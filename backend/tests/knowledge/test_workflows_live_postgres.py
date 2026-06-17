from __future__ import annotations

import asyncio
import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select

from deerflow.config.paths import Paths
from deerflow.knowledge.config import KnowledgeDatabaseConfig
from deerflow.knowledge.database import KnowledgeDatabase
from deerflow.knowledge.enums import WorkflowStatus
from deerflow.knowledge.models import Artifact, ArtifactEvidenceLink, WorkflowArtifact, WorkflowRun, WorkflowStepRun
from deerflow.knowledge.workflows import (
    ArtifactWriteRequest,
    HandlerRegistry,
    StepHandlerContext,
    StepHandlerResult,
    StepOutputKind,
    WorkflowArtifactService,
    WorkflowEngine,
    WorkflowType,
)

pytestmark = pytest.mark.skipif(not os.getenv("KNOWLEDGE_WORKFLOW_TEST_DATABASE_URL"), reason="KNOWLEDGE_WORKFLOW_TEST_DATABASE_URL is not set")


class RecordingHandler:
    def __init__(self, *, requires_approval: bool = False) -> None:
        self.calls: list[StepHandlerContext] = []
        self.requires_approval = requires_approval

    async def __call__(self, context: StepHandlerContext) -> StepHandlerResult:
        self.calls.append(context)
        if context.step_key == "create_action_draft":
            return StepHandlerResult(
                {
                    "action_draft": {
                        "proposed_action": "create_task",
                        "parameters_preview": {"title": "Review evidence"},
                        "risk": "low",
                        "requires_approval": True,
                        "executed": False,
                    }
                },
                output_kind=StepOutputKind.ACTION_DRAFT,
                requires_approval=True,
            )
        return StepHandlerResult({"step": context.step_key, "attempt": context.attempt})


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


def _handlers() -> tuple[HandlerRegistry, dict[str, RecordingHandler]]:
    handlers = {
        "retrieve_evidence": RecordingHandler(),
        "analyze_evidence": RecordingHandler(),
        "review_knowledge_update": RecordingHandler(),
        "create_action_draft": RecordingHandler(requires_approval=True),
        "persist_artifact": RecordingHandler(),
    }
    return HandlerRegistry(handlers), handlers


def test_workflow_domain_live_postgres_migrations_engine_and_artifacts(tmp_path: Path) -> None:
    url = os.environ["KNOWLEDGE_WORKFLOW_TEST_DATABASE_URL"]
    cfg = _alembic_config(url)
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "heads")

    async def run() -> None:
        db = await _initialized_db(url)
        workspace_id = uuid4()
        registry, handlers = _handlers()
        engine = WorkflowEngine(db.session_factory, handlers=registry)

        created = await engine.create(
            workspace_id=workspace_id,
            workflow_type=WorkflowType.DECISION_MEMO,
            input_payload={"decision": "Choose storage boundary", "user_id": "user-a", "thread_id": "thread-a"},
            idempotency_key="decision-memo-storage",
        )
        duplicate = await engine.create(
            workspace_id=workspace_id,
            workflow_type=WorkflowType.DECISION_MEMO,
            input_payload={"decision": "Choose storage boundary", "user_id": "user-a", "thread_id": "thread-a"},
            idempotency_key="decision-memo-storage",
        )
        completed = await engine.advance(workspace_id=workspace_id, workflow_run_id=created.workflow_run_id)
        repeated = await engine.advance(workspace_id=workspace_id, workflow_run_id=created.workflow_run_id)

        assert duplicate.workflow_run_id == created.workflow_run_id
        assert completed.status == WorkflowStatus.COMPLETED, completed.error
        assert repeated.status == WorkflowStatus.COMPLETED
        assert len(handlers["retrieve_evidence"].calls) == 1
        assert len(handlers["analyze_evidence"].calls) == 1
        assert len(handlers["persist_artifact"].calls) == 1

        action_created = await engine.create(
            workspace_id=workspace_id,
            workflow_type=WorkflowType.KNOWLEDGE_TO_ACTION,
            input_payload={"objective": "prepare follow-up", "user_id": "user-a", "thread_id": "thread-a"},
        )
        action_result = await engine.advance(workspace_id=workspace_id, workflow_run_id=action_created.workflow_run_id)
        assert action_result.status == WorkflowStatus.REQUIRES_APPROVAL
        assert action_result.step_outputs["create_action_draft"]["action_draft"]["executed"] is False

        artifact_service = WorkflowArtifactService(db.session_factory, paths=Paths(base_dir=tmp_path / ".deer-flow"))
        request = ArtifactWriteRequest(
            workspace_id=workspace_id,
            workflow_run_id=created.workflow_run_id,
            user_id="user-a",
            thread_id="thread-a",
            artifact_type="decision_memo",
            title="Decision Memo",
            json_payload={"decision": "Use user-scoped storage"},
            markdown="# Decision Memo\n",
            idempotency_key="decision-memo-storage",
        )
        artifact = await artifact_service.persist_artifact(request)
        duplicate_artifact = await artifact_service.persist_artifact(request)
        assert duplicate_artifact.artifact_id == artifact.artifact_id

        async with db.session_factory() as session:
            run = await session.get(WorkflowRun, created.workflow_run_id)
            assert run is not None
            assert run.workspace_id == workspace_id
            assert run.status == WorkflowStatus.COMPLETED
            assert run.idempotency_key == "decision-memo-storage"
            assert await session.scalar(select(func.count()).select_from(WorkflowStepRun).where(WorkflowStepRun.workflow_run_id == run.id)) == 3
            assert await session.scalar(select(func.count()).select_from(WorkflowArtifact).where(WorkflowArtifact.workflow_run_id == run.id)) == 1
            assert await session.scalar(select(func.count()).select_from(Artifact).where(Artifact.id == artifact.artifact_id)) == 1
            assert await session.scalar(select(func.count()).select_from(ArtifactEvidenceLink).where(ArtifactEvidenceLink.artifact_id == artifact.artifact_id)) == 1

        await db.dispose()

    try:
        asyncio.run(run())
    finally:
        command.downgrade(cfg, "base")
        command.upgrade(cfg, "heads")
