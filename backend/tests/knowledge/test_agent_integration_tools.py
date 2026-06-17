from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
import yaml

from deerflow.config.app_config import AppConfig
from deerflow.config.sandbox_config import SandboxConfig
from deerflow.config.subagents_config import SubagentsAppConfig
from deerflow.knowledge.runtime import (
    TrustedKnowledgeContext,
    reset_knowledge_service_provider,
    set_knowledge_service_provider,
)
from deerflow.skills.storage import get_or_new_skill_storage, reset_skill_storage
from deerflow.subagents.registry import get_subagent_config
from deerflow.tools.builtins.knowledge_tools import KNOWLEDGE_TOOLS, action_execute, approval_decide, knowledge_ingest, knowledge_search
from deerflow.tools.builtins.tool_search import assemble_deferred_tools
from deerflow.tools.tools import get_available_tools

EXPECTED_KNOWLEDGE_TOOL_NAMES = {
    "knowledge_ingest",
    "knowledge_ingestion_status",
    "knowledge_search",
    "knowledge_analyze",
    "knowledge_get_source",
    "knowledge_get_revision",
    "knowledge_get_claims",
    "knowledge_expand_graph",
    "knowledge_compare_revisions",
    "knowledge_find_conflicts",
    "knowledge_generate_update_report",
    "workflow_create",
    "workflow_get",
    "workflow_advance",
    "workflow_generate_artifact",
    "approval_request",
    "approval_get",
    "approval_decide",
    "action_preview",
    "action_execute",
    "knowledge_artifact_validate",
    "knowledge_provenance_validate",
    "workflow_validate",
    "approval_validate",
}


class FakeKnowledgeProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[str, TrustedKnowledgeContext, object]] = []
        self.executions = 0
        self.approved = False
        self.payload_tampered = False

    async def initialize(self) -> None:
        return None

    async def dispose(self) -> None:
        return None

    async def ingest(self, context, payload):
        self.calls.append(("ingest", context, payload))
        return {"job_id": "job-1", "source_id": "source-1", "revision_id": "revision-1", "status": "succeeded"}

    async def ingestion_status(self, context, job_id):
        self.calls.append(("ingestion_status", context, job_id))
        return {"job_id": job_id, "status": "succeeded"}

    async def search(self, context, payload):
        self.calls.append(("search", context, payload))
        return {
            "direct_evidence": [{"id": "chunk-1", "text": "fact", "citation": {"source_id": "source-1"}}],
            "parent_context": [],
            "warnings": [],
        }

    async def analyze(self, context, payload):
        self.calls.append(("analyze", context, payload))
        return {"supported_facts": [], "inferred_conclusions": [], "unsupported_claims": [], "markdown": ""}

    async def get_source(self, context, source_id):
        self.calls.append(("get_source", context, source_id))
        return {"source_id": source_id}

    async def get_revision(self, context, revision_id):
        self.calls.append(("get_revision", context, revision_id))
        return {"revision_id": revision_id}

    async def get_claims(self, context, payload):
        self.calls.append(("get_claims", context, payload))
        return {"claims": []}

    async def expand_graph(self, context, payload):
        self.calls.append(("expand_graph", context, payload))
        return {"nodes": [], "edges": []}

    async def compare_revisions(self, context, payload):
        self.calls.append(("compare_revisions", context, payload))
        return {"changes": []}

    async def find_conflicts(self, context, payload):
        self.calls.append(("find_conflicts", context, payload))
        return {"conflicts": []}

    async def generate_update_report(self, context, payload):
        self.calls.append(("generate_update_report", context, payload))
        return {"markdown": "", "conflicts": []}

    async def workflow_create(self, context, payload):
        self.calls.append(("workflow_create", context, payload))
        return {"workflow_run_id": "workflow-1", "status": "ready"}

    async def workflow_get(self, context, workflow_run_id):
        self.calls.append(("workflow_get", context, workflow_run_id))
        return {"workflow_run_id": workflow_run_id, "status": "ready"}

    async def workflow_advance(self, context, workflow_run_id):
        self.calls.append(("workflow_advance", context, workflow_run_id))
        return {"workflow_run_id": workflow_run_id, "status": "requires_approval"}

    async def workflow_generate_artifact(self, context, payload):
        self.calls.append(("workflow_generate_artifact", context, payload))
        return {"artifact_id": "artifact-1", "storage_path": "/mnt/user-data/outputs/report.md"}

    async def approval_request(self, context, payload):
        self.calls.append(("approval_request", context, payload))
        return {"approval_request_id": "approval-1", "status": "awaiting_approval"}

    async def approval_get(self, context, approval_request_id):
        self.calls.append(("approval_get", context, approval_request_id))
        return {"approval_request_id": approval_request_id, "status": "approved" if self.approved else "awaiting_approval"}

    async def approval_decide(self, context, payload):
        self.calls.append(("approval_decide", context, payload))
        if payload["decision"] == "approve":
            self.approved = True
            return {"approval_request_id": payload["approval_request_id"], "status": "approved", "actor_id": context.actor_id}
        return {"approval_request_id": payload["approval_request_id"], "status": payload["decision"] + "ed"}

    async def action_preview(self, context, payload):
        self.calls.append(("action_preview", context, payload))
        return {"side_effect": False, "preview": payload}

    async def action_execute(self, context, approval_request_id):
        self.calls.append(("action_execute", context, approval_request_id))
        if not self.approved:
            raise ValueError("ApprovalRequest is not approved")
        if self.payload_tampered:
            raise ValueError("Action payload changed after approval")
        if self.executions == 0:
            self.executions += 1
        return {"approval_request_id": approval_request_id, "status": "succeeded", "adapter_calls": self.executions}

    async def validate_artifact(self, context, payload):
        self.calls.append(("validate_artifact", context, payload))
        return {"issues": []}

    async def validate_provenance(self, context, payload):
        self.calls.append(("validate_provenance", context, payload))
        return {"issues": []}

    async def validate_workflow(self, context, payload):
        self.calls.append(("validate_workflow", context, payload))
        return {"issues": []}

    async def validate_approval(self, context, payload):
        self.calls.append(("validate_approval", context, payload))
        return {"issues": []}


def _runtime(workspace_id=None, *, user_id: str = "user-1", thread_id: str = "thread-1", actor_id: str = "actor-1"):
    return SimpleNamespace(
        context={
            "workspace_id": str(workspace_id or uuid4()),
            "user_id": user_id,
            "thread_id": thread_id,
            "actor_id": actor_id,
        },
        state={"thread_data": {}},
        config={"configurable": {"thread_id": thread_id}},
    )


def test_knowledge_tools_are_registered_and_schema_hides_trusted_context(monkeypatch) -> None:
    app_config = AppConfig(
        sandbox=SandboxConfig(use="deerflow.sandbox.local:LocalSandboxProvider"),
        tools=[],
        models=[],
    )
    monkeypatch.setattr("deerflow.tools.tools.is_host_bash_allowed", lambda _config=None: True)

    tools = get_available_tools(include_mcp=False, app_config=app_config)
    names = {item.name for item in tools}
    knowledge_names = [item.name for item in KNOWLEDGE_TOOLS]

    assert EXPECTED_KNOWLEDGE_TOOL_NAMES <= names
    assert set(knowledge_names) == EXPECTED_KNOWLEDGE_TOOL_NAMES
    assert len(knowledge_names) == len(EXPECTED_KNOWLEDGE_TOOL_NAMES) == 24
    assert len(knowledge_names) == len(set(knowledge_names))
    for item in KNOWLEDGE_TOOLS:
        assert "workspace_id" not in item.args
        assert "user_id" not in item.args
        assert "thread_id" not in item.args
        assert "actor_id" not in item.args


def test_knowledge_tools_are_not_deferred_mcp_aliases() -> None:
    final_tools, deferred_setup = assemble_deferred_tools(list(KNOWLEDGE_TOOLS), enabled=True)

    assert {tool.name for tool in final_tools} == EXPECTED_KNOWLEDGE_TOOL_NAMES
    assert deferred_setup.deferred_names == frozenset()
    assert {tool.name for tool in final_tools if tool.name == "tool_search"} == set()


@pytest.mark.asyncio
async def test_tools_use_trusted_context_and_fake_services() -> None:
    provider = FakeKnowledgeProvider()
    set_knowledge_service_provider(provider)
    runtime = _runtime()
    try:
        result = await knowledge_search.coroutine(runtime, "roadmap", {"source_type": "note"}, 1000)
        decision = await approval_decide.coroutine(runtime, "approval-1", "approve", "ship it")
        first = await action_execute.coroutine(runtime, "approval-1")
        second = await action_execute.coroutine(runtime, "approval-1")
    finally:
        reset_knowledge_service_provider()

    assert result["ok"] is True
    assert decision["actor_id"] == "actor-1"
    assert first["adapter_calls"] == 1
    assert second["adapter_calls"] == 1
    call_name, context, payload = provider.calls[0]
    assert call_name == "search"
    assert context.user_id == "user-1"
    assert context.thread_id == "thread-1"
    assert payload["query"] == "roadmap"


@pytest.mark.asyncio
async def test_tools_reject_model_supplied_host_paths_and_missing_workspace() -> None:
    provider = FakeKnowledgeProvider()
    set_knowledge_service_provider(provider)
    try:
        host_path_result = await knowledge_ingest.coroutine(_runtime(), "file", "/Users/Apple/secret.pdf", None, None)
        missing_context_result = await knowledge_search.coroutine(SimpleNamespace(context={}, state={}, config={}), "q", None, 4000)
    finally:
        reset_knowledge_service_provider()

    assert host_path_result["ok"] is False
    assert "virtual paths" in host_path_result["message"]
    assert missing_context_result["ok"] is False
    assert "Trusted" in missing_context_result["message"]


@pytest.mark.asyncio
async def test_action_execute_requires_approval_and_rejects_tampered_payload() -> None:
    provider = FakeKnowledgeProvider()
    set_knowledge_service_provider(provider)
    runtime = _runtime()
    try:
        unapproved = await action_execute.coroutine(runtime, "approval-1")
        await approval_decide.coroutine(runtime, "approval-1", "approve", None)
        provider.payload_tampered = True
        tampered = await action_execute.coroutine(runtime, "approval-1")
    finally:
        reset_knowledge_service_provider()

    assert unapproved["ok"] is False
    assert "not approved" in unapproved["message"]
    assert tampered["ok"] is False
    assert "changed after approval" in tampered["message"]


def test_personal_knowledge_skill_is_scanned_from_production_public_path(monkeypatch) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    monkeypatch.setenv("DEER_FLOW_PROJECT_ROOT", str(repo_root))
    reset_skill_storage()
    app_config = AppConfig(
        sandbox=SandboxConfig(use="deerflow.sandbox.local:LocalSandboxProvider"),
        tools=[],
        models=[],
    )
    storage = get_or_new_skill_storage(app_config=app_config)

    skills = {skill.name: skill for skill in storage.load_skills(enabled_only=False)}

    skill = skills["personal-knowledge-agent"]
    assert "knowledge_search" in (skill.allowed_tools or [])
    assert "action_execute" in (skill.allowed_tools or [])
    assert storage.get_skills_root_path() == repo_root / "skills"


def test_personal_knowledge_subagent_example_parses_with_minimal_tools() -> None:
    snippet = Path("../docs/personal-knowledge-agent/examples/subagents.personal-knowledge-agent.yaml")
    data = yaml.safe_load(snippet.read_text(encoding="utf-8"))
    config = SubagentsAppConfig.model_validate(data["subagents"])

    curator = get_subagent_config("knowledge-curator", app_config=config)
    researcher = get_subagent_config("knowledge-researcher", app_config=config)
    auditor = get_subagent_config("contradiction-auditor", app_config=config)
    operator = get_subagent_config("workflow-operator", app_config=config)

    assert curator is not None and "knowledge_ingest" in (curator.tools or [])
    assert researcher is not None and "approval_decide" not in (researcher.tools or [])
    assert auditor is not None and "action_execute" not in (auditor.tools or [])
    assert operator is not None and "action_execute" in (operator.tools or [])

    role_tools = set()
    for agent in (config.custom_agents or {}).values():
        role_tools.update(agent.tools or [])
    assert role_tools <= EXPECTED_KNOWLEDGE_TOOL_NAMES
    assert "task" not in role_tools
