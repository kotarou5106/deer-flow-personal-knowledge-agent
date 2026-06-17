from __future__ import annotations

import asyncio
import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select

from deerflow.knowledge.actions import ActionAdapterRegistry, ActionDraft, ActionExecutionService, ActionType, ApprovalService, RecordingFakeAdapter
from deerflow.knowledge.config import KnowledgeDatabaseConfig
from deerflow.knowledge.database import KnowledgeDatabase
from deerflow.knowledge.enums import ActionExecutionStatus, ApprovalStatus, RiskLevel, WorkflowStatus
from deerflow.knowledge.models import ActionExecution, ApprovalRequest, AuditLog, WorkflowRun, WorkflowStepRun

pytestmark = pytest.mark.skipif(not os.getenv("KNOWLEDGE_ACTION_TEST_DATABASE_URL"), reason="KNOWLEDGE_ACTION_TEST_DATABASE_URL is not set")


class SlowFakeAdapter(RecordingFakeAdapter):
    async def execute(self, action, idempotency_key):
        await asyncio.sleep(0.05)
        return await super().execute(action, idempotency_key)


def _alembic_config(url: str) -> Config:
    script = Path.cwd() / "packages/harness/deerflow/persistence/migrations"
    cfg = Config(str(script / "alembic.ini"))
    cfg.set_main_option("script_location", str(script))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


async def _initialized_db(url: str) -> KnowledgeDatabase:
    db = KnowledgeDatabase(KnowledgeDatabaseConfig(database_url=url))
    await db.initialize()
    return db


async def _seed_workflow(db: KnowledgeDatabase, workspace_id):
    workflow_run_id = uuid4()
    step_run_id = uuid4()
    async with db.session_factory() as session:
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


def _draft(workflow_run_id, step_run_id):
    return ActionDraft(
        action_type=ActionType.TASK_CREATE,
        target="task-board",
        payload={"title": "Review grounded answer"},
        preview={"title": "Review grounded answer"},
        risk_level=RiskLevel.LOW,
        requires_approval=True,
        source_workflow_run_id=workflow_run_id,
        source_step_run_id=step_run_id,
    )


def test_action_execution_live_postgres_migrations_lifecycle_and_concurrency() -> None:
    url = os.environ["KNOWLEDGE_ACTION_TEST_DATABASE_URL"]
    cfg = _alembic_config(url)
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "heads")

    async def run() -> None:
        db = await _initialized_db(url)
        workspace_id = uuid4()
        workflow_run_id, step_run_id = await _seed_workflow(db, workspace_id)
        approval_service = ApprovalService(db.session_factory)
        adapter = SlowFakeAdapter(external_reference_prefix="task")
        execution_service = ActionExecutionService(db.session_factory, adapters=ActionAdapterRegistry({"task": adapter}))

        requested = await approval_service.request_approval(workspace_id=workspace_id, action_draft=_draft(workflow_run_id, step_run_id), actor_id="agent")
        approved = await approval_service.approve(workspace_id=workspace_id, approval_request_id=requested.approval_request_id, actor_id="user-1")
        assert approved.status == ApprovalStatus.APPROVED

        results = await asyncio.gather(
            execution_service.execute(workspace_id=workspace_id, approval_request_id=requested.approval_request_id),
            execution_service.execute(workspace_id=workspace_id, approval_request_id=requested.approval_request_id),
        )
        assert len(adapter.calls) == 1
        assert {result.action_execution_id for result in results} == {results[0].action_execution_id}

        async with db.session_factory() as session:
            approval = await session.get(ApprovalRequest, requested.approval_request_id)
            execution = await session.get(ActionExecution, results[0].action_execution_id)
            workflow = await session.get(WorkflowRun, workflow_run_id)
            assert approval.status == ApprovalStatus.SUCCEEDED
            assert execution.status == ActionExecutionStatus.SUCCEEDED
            assert execution.external_reference.startswith("task:")
            assert workflow.status == WorkflowStatus.COMPLETED
            assert await session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.workspace_id == workspace_id)) >= 4

        await db.dispose()

    try:
        asyncio.run(run())
    finally:
        command.downgrade(cfg, "base")
        command.upgrade(cfg, "heads")
