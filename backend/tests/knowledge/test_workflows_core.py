from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from deerflow.config.paths import Paths
from deerflow.knowledge.enums import WorkflowStatus
from deerflow.knowledge.models import ActionExecution, Artifact, ArtifactEvidenceLink, KnowledgeBase, WorkflowRun, WorkflowStepRun
from deerflow.knowledge.models.base import Vector
from deerflow.knowledge.workflows import (
    WORKFLOW_DEFINITIONS,
    ArtifactWriteRequest,
    HandlerRegistry,
    StepHandlerContext,
    StepHandlerResult,
    StepOutputKind,
    WorkflowArtifactService,
    WorkflowDefinitionRegistry,
    WorkflowEngine,
    WorkflowType,
    assert_transition_allowed,
)


@compiles(TSVECTOR, "sqlite")
def _compile_tsvector_sqlite(_element, _compiler, **_kw):
    return "TEXT"


@compiles(Vector, "sqlite")
def _compile_vector_sqlite(_element, _compiler, **_kw):
    return "TEXT"


async def _session_factory(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'knowledge-workflows.db'}")

    @event.listens_for(engine.sync_engine, "connect")
    def _register_btrim(dbapi_connection, _):
        dbapi_connection.create_function("btrim", 1, lambda value: str(value).strip() if value is not None else None)

    async with engine.begin() as conn:
        await conn.run_sync(KnowledgeBase.metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


class RecordingHandler:
    def __init__(self, *, fail_once: bool = False, invalid: bool = False, requires_approval: bool = False) -> None:
        self.calls: list[StepHandlerContext] = []
        self.fail_once = fail_once
        self.invalid = invalid
        self.requires_approval = requires_approval

    async def __call__(self, context: StepHandlerContext):
        self.calls.append(context)
        if self.fail_once and len(self.calls) == 1:
            raise RuntimeError("planned failure")
        if self.invalid:
            return {"not": "a StepHandlerResult"}
        payload = {"step": context.step_key, "call_count": len(self.calls)}
        if context.step_key == "create_action_draft":
            payload = {
                "action_draft": {
                    "proposed_action": "send_email",
                    "parameters_preview": {"to": "review@example.com"},
                    "risk": "medium",
                    "requires_approval": True,
                    "executed": False,
                }
            }
        return StepHandlerResult(payload, output_kind=StepOutputKind.ACTION_DRAFT if context.step_key == "create_action_draft" else StepOutputKind.DATA, requires_approval=self.requires_approval)


def _handlers(**overrides: RecordingHandler) -> tuple[HandlerRegistry, dict[str, RecordingHandler]]:
    handlers = {
        "retrieve_evidence": RecordingHandler(),
        "analyze_evidence": RecordingHandler(),
        "review_knowledge_update": RecordingHandler(),
        "create_action_draft": RecordingHandler(requires_approval=True),
        "persist_artifact": RecordingHandler(),
        **overrides,
    }
    return HandlerRegistry(handlers), handlers


def test_all_workflow_definitions_declare_required_contracts() -> None:
    assert {definition.workflow_type for definition in WORKFLOW_DEFINITIONS} == set(WorkflowType)
    for definition in WORKFLOW_DEFINITIONS:
        assert definition.input_schema.required_fields
        assert definition.ordered_steps
        assert definition.required_handlers
        assert definition.artifact_outputs
        assert definition.completion_conditions
        assert all(step.handler_name in definition.required_handlers for step in definition.ordered_steps)


def test_input_schema_validation_rejects_missing_required_fields() -> None:
    definition = WorkflowDefinitionRegistry().get(WorkflowType.TOPIC_DOSSIER)
    with pytest.raises(ValueError, match="topic"):
        definition.input_schema.validate({"user_id": "u", "thread_id": "t"})


def test_illegal_state_transition_is_rejected() -> None:
    with pytest.raises(ValueError, match="Illegal workflow status transition"):
        assert_transition_allowed(WorkflowStatus.COMPLETED, WorkflowStatus.RUNNING)
    assert_transition_allowed(WorkflowStatus.RUNNING, WorkflowStatus.PAUSED)


@pytest.mark.asyncio
async def test_engine_executes_multistep_workflow_and_skips_successful_steps(tmp_path: Path) -> None:
    engine, session_factory = await _session_factory(tmp_path)
    registry, handlers = _handlers()
    workflow_engine = WorkflowEngine(session_factory, handlers=registry)
    workspace_id = uuid4()

    created = await workflow_engine.create(
        workspace_id=workspace_id,
        workflow_type=WorkflowType.TOPIC_DOSSIER,
        input_payload={"topic": "Acme", "user_id": "user-a", "thread_id": "thread-a"},
        idempotency_key="same-topic",
    )
    duplicate = await workflow_engine.create(
        workspace_id=workspace_id,
        workflow_type=WorkflowType.TOPIC_DOSSIER,
        input_payload={"topic": "Acme", "user_id": "user-a", "thread_id": "thread-a"},
        idempotency_key="same-topic",
    )
    result = await workflow_engine.advance(workspace_id=workspace_id, workflow_run_id=created.workflow_run_id)
    again = await workflow_engine.advance(workspace_id=workspace_id, workflow_run_id=created.workflow_run_id)

    assert duplicate.workflow_run_id == created.workflow_run_id
    assert result.status == WorkflowStatus.COMPLETED
    assert again.status == WorkflowStatus.COMPLETED
    assert len(handlers["retrieve_evidence"].calls) == 1
    assert len(handlers["analyze_evidence"].calls) == 1
    assert len(handlers["persist_artifact"].calls) == 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_engine_records_failure_and_retries_failed_step(tmp_path: Path) -> None:
    engine, session_factory = await _session_factory(tmp_path)
    registry, handlers = _handlers(analyze_evidence=RecordingHandler(fail_once=True))
    workflow_engine = WorkflowEngine(session_factory, handlers=registry)
    workspace_id = uuid4()

    created = await workflow_engine.create(
        workspace_id=workspace_id,
        workflow_type=WorkflowType.TOPIC_DOSSIER,
        input_payload={"topic": "Acme", "user_id": "user-a", "thread_id": "thread-a"},
    )
    failed = await workflow_engine.advance(workspace_id=workspace_id, workflow_run_id=created.workflow_run_id)
    retried = await workflow_engine.retry_failed_step(workspace_id=workspace_id, workflow_run_id=created.workflow_run_id)

    assert failed.status == WorkflowStatus.FAILED
    assert retried.status == WorkflowStatus.COMPLETED
    assert len(handlers["retrieve_evidence"].calls) == 1
    assert len(handlers["analyze_evidence"].calls) == 2
    async with session_factory() as session:
        step = await session.scalar(select(WorkflowStepRun).where(WorkflowStepRun.step_key == "analyze_evidence"))
        assert step.attempt == 2
        assert step.error_message is None
    await engine.dispose()


@pytest.mark.asyncio
async def test_pause_resume_and_workspace_isolation(tmp_path: Path) -> None:
    engine, session_factory = await _session_factory(tmp_path)
    workflow_engine = WorkflowEngine(session_factory, handlers=_handlers()[0])
    workspace_id = uuid4()
    other_workspace_id = uuid4()
    created = await workflow_engine.create(
        workspace_id=workspace_id,
        workflow_type=WorkflowType.TOPIC_DOSSIER,
        input_payload={"topic": "Acme", "user_id": "user-a", "thread_id": "thread-a"},
    )
    async with session_factory() as session:
        run = await session.get(WorkflowRun, created.workflow_run_id)
        run.status = WorkflowStatus.RUNNING
        await session.commit()

    paused = await workflow_engine.pause(workspace_id=workspace_id, workflow_run_id=created.workflow_run_id)
    resumed = await workflow_engine.resume(workspace_id=workspace_id, workflow_run_id=created.workflow_run_id)

    assert paused.status == WorkflowStatus.PAUSED
    assert resumed.status == WorkflowStatus.COMPLETED
    with pytest.raises(ValueError, match="workspace"):
        await workflow_engine.advance(workspace_id=other_workspace_id, workflow_run_id=created.workflow_run_id)
    await engine.dispose()


@pytest.mark.asyncio
async def test_missing_or_invalid_handler_output_fails_deterministically(tmp_path: Path) -> None:
    engine, session_factory = await _session_factory(tmp_path)
    workspace_id = uuid4()

    with pytest.raises(ValueError, match="Missing workflow handler"):
        await WorkflowEngine(session_factory, handlers=HandlerRegistry({})).create(
            workspace_id=workspace_id,
            workflow_type=WorkflowType.TOPIC_DOSSIER,
            input_payload={"topic": "Acme", "user_id": "user-a", "thread_id": "thread-a"},
        )

    workflow_engine = WorkflowEngine(session_factory, handlers=_handlers(retrieve_evidence=RecordingHandler(invalid=True))[0])
    created = await workflow_engine.create(
        workspace_id=workspace_id,
        workflow_type=WorkflowType.TOPIC_DOSSIER,
        input_payload={"topic": "Acme", "user_id": "user-a", "thread_id": "thread-a"},
    )
    failed = await workflow_engine.advance(workspace_id=workspace_id, workflow_run_id=created.workflow_run_id)
    assert failed.status == WorkflowStatus.FAILED
    await engine.dispose()


@pytest.mark.asyncio
async def test_knowledge_to_action_creates_draft_and_does_not_execute_external_action(tmp_path: Path) -> None:
    engine, session_factory = await _session_factory(tmp_path)
    workflow_engine = WorkflowEngine(session_factory, handlers=_handlers()[0])
    workspace_id = uuid4()

    created = await workflow_engine.create(
        workspace_id=workspace_id,
        workflow_type=WorkflowType.KNOWLEDGE_TO_ACTION,
        input_payload={"objective": "follow up", "user_id": "user-a", "thread_id": "thread-a"},
    )
    result = await workflow_engine.advance(workspace_id=workspace_id, workflow_run_id=created.workflow_run_id)

    assert result.status == WorkflowStatus.REQUIRES_APPROVAL
    assert result.step_outputs["create_action_draft"]["action_draft"]["executed"] is False
    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(ActionExecution).where(ActionExecution.workspace_id == workspace_id)) == 0
    await engine.dispose()


@pytest.mark.asyncio
async def test_artifact_service_writes_json_markdown_records_and_evidence_links(tmp_path: Path) -> None:
    engine, session_factory = await _session_factory(tmp_path)
    workspace_id = uuid4()
    workflow_run_id = uuid4()
    paths = Paths(base_dir=tmp_path / ".deer-flow")
    service = WorkflowArtifactService(session_factory, paths=paths)

    async with session_factory() as session:
        session.add(WorkflowRun(id=workflow_run_id, workspace_id=workspace_id, workflow_type="topic_dossier", input={}, status=WorkflowStatus.RUNNING))
        await session.commit()

    request = ArtifactWriteRequest(
        workspace_id=workspace_id,
        workflow_run_id=workflow_run_id,
        user_id="user-a",
        thread_id="thread-a",
        artifact_type="topic_dossier",
        title="Topic Dossier: Acme",
        json_payload={"answer": "Acme"},
        markdown="# Acme\n",
        idempotency_key="topic-dossier-acme",
    )
    first = await service.persist_artifact(request)
    second = await service.persist_artifact(request)

    assert second.artifact_id == first.artifact_id
    assert first.storage_path.startswith("/mnt/user-data/outputs/knowledge-workflows/")
    assert paths.resolve_virtual_path("thread-a", first.storage_path, user_id="user-a").read_text(encoding="utf-8")
    assert paths.resolve_virtual_path("thread-a", first.markdown_storage_path, user_id="user-a").read_text(encoding="utf-8") == "# Acme\n"
    async with session_factory() as session:
        artifact = await session.get(Artifact, first.artifact_id)
        assert artifact is not None
        assert await session.scalar(select(func.count()).select_from(ArtifactEvidenceLink).where(ArtifactEvidenceLink.artifact_id == first.artifact_id)) == 1
    await engine.dispose()
