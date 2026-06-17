from __future__ import annotations

import asyncio
import os
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config

from deerflow.config.app_config import AppConfig
from deerflow.config.sandbox_config import SandboxConfig
from deerflow.knowledge.config import KnowledgeDatabaseConfig
from deerflow.knowledge.database import KnowledgeDatabase
from deerflow.knowledge.enums import ApprovalStatus, RiskLevel, WorkflowStatus
from deerflow.knowledge.models import ApprovalRequest, Source, WorkflowRun
from deerflow.knowledge.runtime import get_knowledge_service_provider, reset_knowledge_service_provider
from deerflow.knowledge.unit_of_work import KnowledgeUnitOfWork
from deerflow.tools.tools import get_available_tools

pytestmark = pytest.mark.skipif(not os.getenv("KNOWLEDGE_TOOL_TEST_DATABASE_URL"), reason="KNOWLEDGE_TOOL_TEST_DATABASE_URL is not set")


def _alembic_config(url: str) -> Config:
    script = Path.cwd() / "packages/harness/deerflow/persistence/migrations"
    cfg = Config(str(script / "alembic.ini"))
    cfg.set_main_option("script_location", str(script))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def _runtime(workspace_id, database_url: str, *, actor_id: str = "live-actor"):
    return SimpleNamespace(
        context={
            "workspace_id": str(workspace_id),
            "user_id": "live-user",
            "thread_id": "live-thread",
            "actor_id": actor_id,
            "knowledge_database_url": database_url,
        },
        state={},
        config={"configurable": {"thread_id": "live-thread"}},
    )


def _registry_tools():
    app_config = AppConfig(
        sandbox=SandboxConfig(use="deerflow.sandbox.local:LocalSandboxProvider"),
        tools=[],
        models=[],
    )
    return {tool.name: tool for tool in get_available_tools(include_mcp=False, app_config=app_config)}


def test_knowledge_tool_live_postgres_production_provider_roundtrip() -> None:
    url = os.environ["KNOWLEDGE_TOOL_TEST_DATABASE_URL"]
    cfg = _alembic_config(url)
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "heads")

    async def run() -> None:
        db = KnowledgeDatabase(KnowledgeDatabaseConfig(database_url=url))
        await db.initialize()
        workspace_a = uuid4()
        workspace_b = uuid4()
        tools = _registry_tools()
        try:
            async with KnowledgeUnitOfWork(db.session_factory) as uow:
                source = await uow.sources.add(
                    Source(
                        workspace_id=workspace_a,
                        source_type="url",
                        canonical_uri="https://example.com/tool-integration",
                        title="Tool Integration Source",
                        metadata_json={"seeded_by": "live-tool-test"},
                    )
                )
                workflow = await uow.workflow_runs.add(
                    WorkflowRun(
                        workspace_id=workspace_a,
                        workflow_type="knowledge-to-action",
                        input={"goal": "verify tool actor"},
                        status=WorkflowStatus.REQUIRES_APPROVAL,
                    )
                )
                approval = await uow.approval_requests.add(
                    ApprovalRequest(
                        workspace_id=workspace_a,
                        workflow_run_id=workflow.id,
                        action_type="email_draft",
                        action_preview={"payload": {"subject": "draft only"}},
                        risk_level=RiskLevel.LOW,
                        status=ApprovalStatus.AWAITING_APPROVAL,
                    )
                )
                unapproved = await uow.approval_requests.add(
                    ApprovalRequest(
                        workspace_id=workspace_a,
                        workflow_run_id=workflow.id,
                        action_type="email_send",
                        action_preview={"payload": {"subject": "blocked"}},
                        risk_level=RiskLevel.HIGH,
                        status=ApprovalStatus.AWAITING_APPROVAL,
                    )
                )
                await uow.commit()

            assert "knowledge_get_source" in tools
            assert "approval_decide" in tools
            assert "action_execute" in tools

            fetched = await tools["knowledge_get_source"].coroutine(_runtime(workspace_a, url), str(source.id))
            assert fetched["canonical_uri"] == "https://example.com/tool-integration"
            isolated = await tools["knowledge_get_source"].coroutine(_runtime(workspace_b, url), str(source.id))
            assert isolated["ok"] is False
            assert "workspace" in isolated["message"]
            decision = await tools["approval_decide"].coroutine(_runtime(workspace_a, url, actor_id="trusted-reviewer"), str(approval.id), "approve", "verified")
            assert decision["ok"] is True
            assert decision["decided_by"] == "trusted-reviewer"
            blocked = await tools["action_execute"].coroutine(_runtime(workspace_a, url), str(unapproved.id))
            assert blocked["ok"] is False
            assert "not approved" in blocked["message"]
        finally:
            await get_knowledge_service_provider().dispose()
            reset_knowledge_service_provider()
            await db.dispose()

    try:
        asyncio.run(run())
    finally:
        command.downgrade(cfg, "base")
        command.upgrade(cfg, "heads")
