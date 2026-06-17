from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import event, select, update
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from deerflow.knowledge.actions import (
    ActionAdapterRegistry,
    ActionDraft,
    ActionExecutionService,
    ActionType,
    ApprovalService,
    RecordingFakeAdapter,
    action_payload_for_storage,
    assert_approval_transition_allowed,
    default_fake_action_adapter_registry,
    validate_action_draft,
)
from deerflow.knowledge.enums import ActionExecutionStatus, ApprovalStatus, RiskLevel, WorkflowStatus
from deerflow.knowledge.models import ActionExecution, ApprovalRequest, AuditLog, KnowledgeBase, WorkflowRun, WorkflowStepRun
from deerflow.knowledge.models.base import Vector


@compiles(TSVECTOR, "sqlite")
def _compile_tsvector_sqlite(_element, _compiler, **_kw):
    return "TEXT"


@compiles(Vector, "sqlite")
def _compile_vector_sqlite(_element, _compiler, **_kw):
    return "TEXT"


async def _session_factory(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'knowledge-actions.db'}")

    @event.listens_for(engine.sync_engine, "connect")
    def _register_btrim(dbapi_connection, _):
        dbapi_connection.create_function("btrim", 1, lambda value: str(value).strip() if value is not None else None)

    async with engine.begin() as conn:
        await conn.run_sync(KnowledgeBase.metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def _seed_workflow(session_factory, workspace_id):
    workflow_run_id = uuid4()
    step_run_id = uuid4()
    async with session_factory() as session:
        session.add(
            WorkflowRun(
                id=workflow_run_id,
                workspace_id=workspace_id,
                workflow_type="knowledge_to_action",
                input={"objective": "follow up"},
                status=WorkflowStatus.REQUIRES_APPROVAL,
            )
        )
        session.add(
            WorkflowStepRun(
                id=step_run_id,
                workspace_id=workspace_id,
                workflow_run_id=workflow_run_id,
                step_key="create_action_draft",
                sequence=2,
                status=WorkflowStatus.SUCCEEDED,
                input_payload={},
                output_payload={},
                attempt=1,
                idempotency_key=f"{workflow_run_id}:create_action_draft:2",
            )
        )
        await session.commit()
    return workflow_run_id, step_run_id


def _draft(workflow_run_id, step_run_id, *, action_type=ActionType.EMAIL_SEND, requires_approval=True, secret=False):
    payload = {"to": "review@example.com", "subject": "Hello", "body": "Draft body"}
    if secret:
        payload["api_token"] = "super-secret"
    return ActionDraft(
        action_type=action_type,
        target="review@example.com",
        payload=payload,
        preview={"subject": "Hello"},
        risk_level=RiskLevel.MEDIUM,
        requires_approval=requires_approval,
        source_workflow_run_id=workflow_run_id,
        source_step_run_id=step_run_id,
    )


def test_action_draft_schema_and_policy_are_deterministic() -> None:
    workflow_run_id = uuid4()
    step_run_id = uuid4()
    action = validate_action_draft(_draft(workflow_run_id, step_run_id, secret=True))

    assert action.action_type == ActionType.EMAIL_SEND
    assert action.requires_approval is True
    assert action.payload_hash
    assert validate_action_draft(_draft(workflow_run_id, step_run_id, action_type=ActionType.EMAIL_DRAFT, requires_approval=False)).requires_approval is False
    with pytest.raises(ValueError, match="require approval"):
        validate_action_draft(_draft(workflow_run_id, step_run_id, requires_approval=False))
    with pytest.raises(ValueError, match="Unknown action type"):
        validate_action_draft({**_draft(workflow_run_id, step_run_id).__dict__, "action_type": "shell_command"})


def test_fake_adapter_registry_whitelists_supported_connectors() -> None:
    registry = default_fake_action_adapter_registry()

    assert registry.names == {"email", "calendar", "task", "artifact_export"}
    with pytest.raises(ValueError, match="Missing action adapter"):
        registry.get("shell")


def test_approval_state_machine_rejects_illegal_transitions() -> None:
    assert_approval_transition_allowed(ApprovalStatus.AWAITING_APPROVAL, ApprovalStatus.APPROVED)
    with pytest.raises(ValueError, match="Illegal approval status transition"):
        assert_approval_transition_allowed(ApprovalStatus.REJECTED, ApprovalStatus.APPROVED)


@pytest.mark.asyncio
async def test_approval_lifecycle_execution_idempotency_audit_and_workspace_isolation(tmp_path: Path) -> None:
    engine, session_factory = await _session_factory(tmp_path)
    workspace_id = uuid4()
    workflow_run_id, step_run_id = await _seed_workflow(session_factory, workspace_id)
    approval_service = ApprovalService(session_factory)
    adapter = RecordingFakeAdapter(external_reference_prefix="email")
    execution_service = ActionExecutionService(session_factory, adapters=ActionAdapterRegistry({"email": adapter}))

    requested = await approval_service.request_approval(workspace_id=workspace_id, action_draft=_draft(workflow_run_id, step_run_id, secret=True), actor_id="agent")
    approved = await approval_service.approve(workspace_id=workspace_id, approval_request_id=requested.approval_request_id, actor_id="user-1", reason="looks good")
    first = await execution_service.execute(workspace_id=workspace_id, approval_request_id=requested.approval_request_id)
    second = await execution_service.execute(workspace_id=workspace_id, approval_request_id=requested.approval_request_id)

    assert approved.status == ApprovalStatus.APPROVED
    assert first.status == ActionExecutionStatus.SUCCEEDED
    assert second.action_execution_id == first.action_execution_id
    assert second.adapter_called is False
    assert len(adapter.calls) == 1
    async with session_factory() as session:
        approval = await session.get(ApprovalRequest, requested.approval_request_id)
        assert approval.status == ApprovalStatus.SUCCEEDED
        assert approval.decided_by == "user-1"
        assert approval.action_payload["payload"]["api_token"] == "[REDACTED]"
        workflow = await session.get(WorkflowRun, workflow_run_id)
        assert workflow.status == WorkflowStatus.COMPLETED
        execution = await session.get(ActionExecution, first.action_execution_id)
        assert execution.external_reference.startswith("email:")
        events = (await session.execute(select(AuditLog.event_type).where(AuditLog.workspace_id == workspace_id).order_by(AuditLog.created_at))).scalars().all()
        assert {"approval_requested", "approval_approved", "execution_started", "execution_succeeded"} <= set(events)
    with pytest.raises(ValueError, match="workspace"):
        await execution_service.execute(workspace_id=uuid4(), approval_request_id=requested.approval_request_id)
    await engine.dispose()


@pytest.mark.asyncio
async def test_reject_cancel_and_unapproved_requests_cannot_execute(tmp_path: Path) -> None:
    engine, session_factory = await _session_factory(tmp_path)
    workspace_id = uuid4()
    workflow_run_id, step_run_id = await _seed_workflow(session_factory, workspace_id)
    approval_service = ApprovalService(session_factory)
    execution_service = ActionExecutionService(session_factory, adapters=ActionAdapterRegistry({"email": RecordingFakeAdapter()}))

    requested = await approval_service.request_approval(workspace_id=workspace_id, action_draft=_draft(workflow_run_id, step_run_id), actor_id="agent")
    with pytest.raises(ValueError, match="not approved"):
        await execution_service.execute(workspace_id=workspace_id, approval_request_id=requested.approval_request_id)
    rejected = await approval_service.reject(workspace_id=workspace_id, approval_request_id=requested.approval_request_id, actor_id="user-1", reason="no")
    assert rejected.status == ApprovalStatus.REJECTED
    with pytest.raises(ValueError, match="not approved"):
        await execution_service.execute(workspace_id=workspace_id, approval_request_id=requested.approval_request_id)
    with pytest.raises(ValueError, match="Illegal approval status transition"):
        await approval_service.approve(workspace_id=workspace_id, approval_request_id=requested.approval_request_id, actor_id="user-1")
    await engine.dispose()


@pytest.mark.asyncio
async def test_payload_tamper_missing_adapter_failure_and_reconciliation(tmp_path: Path) -> None:
    engine, session_factory = await _session_factory(tmp_path)
    workspace_id = uuid4()
    workflow_run_id, step_run_id = await _seed_workflow(session_factory, workspace_id)
    approval_service = ApprovalService(session_factory)

    requested = await approval_service.request_approval(workspace_id=workspace_id, action_draft=_draft(workflow_run_id, step_run_id), actor_id="agent")
    await approval_service.approve(workspace_id=workspace_id, approval_request_id=requested.approval_request_id, actor_id="user-1")
    async with session_factory() as session:
        tampered_payload = action_payload_for_storage(validate_action_draft(_draft(workflow_run_id, step_run_id)))
        tampered_payload["payload"] = {"to": "attacker@example.com"}
        await session.execute(update(ApprovalRequest).where(ApprovalRequest.id == requested.approval_request_id).values(action_payload=tampered_payload))
        await session.commit()
    with pytest.raises(ValueError, match="reapproved"):
        await ActionExecutionService(session_factory, adapters=ActionAdapterRegistry({"email": RecordingFakeAdapter()})).execute(workspace_id=workspace_id, approval_request_id=requested.approval_request_id)

    second = await approval_service.request_approval(workspace_id=workspace_id, action_draft=_draft(workflow_run_id, step_run_id), actor_id="agent")
    await approval_service.approve(workspace_id=workspace_id, approval_request_id=second.approval_request_id, actor_id="user-1")
    with pytest.raises(ValueError, match="Missing action adapter"):
        await ActionExecutionService(session_factory, adapters=ActionAdapterRegistry({})).execute(workspace_id=workspace_id, approval_request_id=second.approval_request_id)

    failing_workflow_run_id, failing_step_run_id = await _seed_workflow(session_factory, workspace_id)
    failing = await approval_service.request_approval(workspace_id=workspace_id, action_draft=_draft(failing_workflow_run_id, failing_step_run_id), actor_id="agent")
    await approval_service.approve(workspace_id=workspace_id, approval_request_id=failing.approval_request_id, actor_id="user-1")
    failed = await ActionExecutionService(session_factory, adapters=ActionAdapterRegistry({"email": RecordingFakeAdapter(succeed=False)})).execute(workspace_id=workspace_id, approval_request_id=failing.approval_request_id)
    assert failed.status == ActionExecutionStatus.FAILED

    uncertain_workflow_run_id, uncertain_step_run_id = await _seed_workflow(session_factory, workspace_id)
    uncertain = await approval_service.request_approval(workspace_id=workspace_id, action_draft=_draft(uncertain_workflow_run_id, uncertain_step_run_id), actor_id="agent")
    await approval_service.approve(workspace_id=workspace_id, approval_request_id=uncertain.approval_request_id, actor_id="user-1")
    reconciliation = await ActionExecutionService(session_factory, adapters=ActionAdapterRegistry({"email": RecordingFakeAdapter(uncertain=True)})).execute(workspace_id=workspace_id, approval_request_id=uncertain.approval_request_id)
    assert reconciliation.status == ActionExecutionStatus.RECONCILIATION_REQUIRED
    assert reconciliation.requires_reconciliation is True
    await engine.dispose()


class SlowFakeAdapter(RecordingFakeAdapter):
    async def execute(self, action, idempotency_key):
        await asyncio.sleep(0.05)
        return await super().execute(action, idempotency_key)


@pytest.mark.asyncio
async def test_concurrent_execute_invokes_adapter_once(tmp_path: Path) -> None:
    engine, session_factory = await _session_factory(tmp_path)
    workspace_id = uuid4()
    workflow_run_id, step_run_id = await _seed_workflow(session_factory, workspace_id)
    approval_service = ApprovalService(session_factory)
    requested = await approval_service.request_approval(workspace_id=workspace_id, action_draft=_draft(workflow_run_id, step_run_id), actor_id="agent")
    await approval_service.approve(workspace_id=workspace_id, approval_request_id=requested.approval_request_id, actor_id="user-1")
    adapter = SlowFakeAdapter()
    service = ActionExecutionService(session_factory, adapters=ActionAdapterRegistry({"email": adapter}))

    results = await asyncio.gather(
        service.execute(workspace_id=workspace_id, approval_request_id=requested.approval_request_id),
        service.execute(workspace_id=workspace_id, approval_request_id=requested.approval_request_id),
    )

    assert len(adapter.calls) == 1
    assert {result.action_execution_id for result in results} == {results[0].action_execution_id}
    await engine.dispose()
