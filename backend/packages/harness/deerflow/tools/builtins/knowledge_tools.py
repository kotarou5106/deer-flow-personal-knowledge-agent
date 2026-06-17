from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Literal

from langchain.tools import tool

from deerflow.config.paths import VIRTUAL_PATH_PREFIX
from deerflow.knowledge.runtime import (
    KnowledgeServiceUnavailableError,
    TrustedKnowledgeContext,
    resolve_knowledge_service_provider,
    resolve_trusted_knowledge_context,
)
from deerflow.tools.types import Runtime

ValidationIssue = dict[str, str]


async def _call_provider(
    runtime: Runtime,
    call: Callable[[TrustedKnowledgeContext], Awaitable[dict[str, Any]]],
) -> dict[str, Any]:
    try:
        context = resolve_trusted_knowledge_context(runtime)
        provider = resolve_knowledge_service_provider(runtime)
        await provider.initialize()
        result = await call(context)
        return {"ok": True, **result}
    except (KnowledgeServiceUnavailableError, ValueError) as exc:
        return {"ok": False, "error_type": exc.__class__.__name__, "message": str(exc)}


def _assert_virtual_file_reference(source_type: str, source_uri: str) -> None:
    if source_type in {"upload", "file"} and not source_uri.startswith(f"{VIRTUAL_PATH_PREFIX}/"):
        raise ValueError("File sources must use DeerFlow virtual paths under /mnt/user-data")


@tool("knowledge_ingest")
async def knowledge_ingest(
    runtime: Runtime,
    source_type: Literal["upload", "file", "url"],
    source_uri: str,
    media_type: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Ingest a file or URL into the Personal Knowledge Agent."""
    try:
        _assert_virtual_file_reference(source_type, source_uri)
    except ValueError as exc:
        return {"ok": False, "error_type": "ValueError", "message": str(exc)}
    payload = {
        "source_type": source_type,
        "source_uri": source_uri,
        "media_type": media_type,
        "metadata": metadata or {},
    }
    return await _call_provider(runtime, lambda context: resolve_knowledge_service_provider(runtime).ingest(context, payload))


@tool("knowledge_ingestion_status")
async def knowledge_ingestion_status(runtime: Runtime, job_id: str) -> dict[str, Any]:
    """Get the current status of a knowledge ingestion job."""
    return await _call_provider(runtime, lambda context: resolve_knowledge_service_provider(runtime).ingestion_status(context, job_id))


@tool("knowledge_search")
async def knowledge_search(runtime: Runtime, query: str, filters: dict[str, Any] | None = None, context_budget: int = 4000) -> dict[str, Any]:
    """Search knowledge and return a bounded evidence context pack."""
    payload = {"query": query, "filters": filters or {}, "context_budget": context_budget}
    return await _call_provider(runtime, lambda context: resolve_knowledge_service_provider(runtime).search(context, payload))


@tool("knowledge_analyze")
async def knowledge_analyze(runtime: Runtime, question: str, filters: dict[str, Any] | None = None, context_budget: int = 6000) -> dict[str, Any]:
    """Analyze a question using retrieved and citation-validated evidence."""
    payload = {"question": question, "filters": filters or {}, "context_budget": context_budget}
    return await _call_provider(runtime, lambda context: resolve_knowledge_service_provider(runtime).analyze(context, payload))


@tool("knowledge_get_source")
async def knowledge_get_source(runtime: Runtime, source_id: str) -> dict[str, Any]:
    """Get metadata for a knowledge source in the trusted workspace."""
    return await _call_provider(runtime, lambda context: resolve_knowledge_service_provider(runtime).get_source(context, source_id))


@tool("knowledge_get_revision")
async def knowledge_get_revision(runtime: Runtime, revision_id: str) -> dict[str, Any]:
    """Get metadata for a document revision in the trusted workspace."""
    return await _call_provider(runtime, lambda context: resolve_knowledge_service_provider(runtime).get_revision(context, revision_id))


@tool("knowledge_get_claims")
async def knowledge_get_claims(runtime: Runtime, source_id: str | None = None, entity_id: str | None = None) -> dict[str, Any]:
    """Get claims scoped to a source or entity."""
    payload = {"source_id": source_id, "entity_id": entity_id}
    return await _call_provider(runtime, lambda context: resolve_knowledge_service_provider(runtime).get_claims(context, payload))


@tool("knowledge_expand_graph")
async def knowledge_expand_graph(runtime: Runtime, seed_ids: list[str], depth: int = 1) -> dict[str, Any]:
    """Expand a bounded knowledge graph neighborhood."""
    payload = {"seed_ids": seed_ids, "depth": depth}
    return await _call_provider(runtime, lambda context: resolve_knowledge_service_provider(runtime).expand_graph(context, payload))


@tool("knowledge_compare_revisions")
async def knowledge_compare_revisions(runtime: Runtime, base_revision_id: str, target_revision_id: str) -> dict[str, Any]:
    """Compare two document revisions."""
    payload = {"base_revision_id": base_revision_id, "target_revision_id": target_revision_id}
    return await _call_provider(runtime, lambda context: resolve_knowledge_service_provider(runtime).compare_revisions(context, payload))


@tool("knowledge_find_conflicts")
async def knowledge_find_conflicts(runtime: Runtime, source_id: str | None = None, entity_id: str | None = None) -> dict[str, Any]:
    """Find unresolved knowledge conflicts."""
    payload = {"source_id": source_id, "entity_id": entity_id}
    return await _call_provider(runtime, lambda context: resolve_knowledge_service_provider(runtime).find_conflicts(context, payload))


@tool("knowledge_generate_update_report")
async def knowledge_generate_update_report(runtime: Runtime, source_id: str | None = None, revision_id: str | None = None) -> dict[str, Any]:
    """Generate an incremental knowledge update report."""
    payload = {"source_id": source_id, "revision_id": revision_id}
    return await _call_provider(runtime, lambda context: resolve_knowledge_service_provider(runtime).generate_update_report(context, payload))


@tool("workflow_create")
async def workflow_create(runtime: Runtime, workflow_type: str, input_payload: dict[str, Any], idempotency_key: str | None = None) -> dict[str, Any]:
    """Create a Personal Knowledge Agent workflow run."""
    payload = {"workflow_type": workflow_type, "input_payload": input_payload, "idempotency_key": idempotency_key}
    return await _call_provider(runtime, lambda context: resolve_knowledge_service_provider(runtime).workflow_create(context, payload))


@tool("workflow_get")
async def workflow_get(runtime: Runtime, workflow_run_id: str) -> dict[str, Any]:
    """Get a workflow run and its persisted step state."""
    return await _call_provider(runtime, lambda context: resolve_knowledge_service_provider(runtime).workflow_get(context, workflow_run_id))


@tool("workflow_advance")
async def workflow_advance(runtime: Runtime, workflow_run_id: str) -> dict[str, Any]:
    """Advance a workflow run by one deterministic domain step."""
    return await _call_provider(runtime, lambda context: resolve_knowledge_service_provider(runtime).workflow_advance(context, workflow_run_id))


@tool("workflow_generate_artifact")
async def workflow_generate_artifact(runtime: Runtime, workflow_run_id: str, artifact_request: dict[str, Any]) -> dict[str, Any]:
    """Persist a workflow artifact using DeerFlow user-scoped storage."""
    payload = {"workflow_run_id": workflow_run_id, "artifact_request": artifact_request}
    return await _call_provider(runtime, lambda context: resolve_knowledge_service_provider(runtime).workflow_generate_artifact(context, payload))


@tool("approval_request")
async def approval_request(
    runtime: Runtime,
    workflow_run_id: str,
    action_type: str,
    target: str,
    payload: dict[str, Any],
    preview: dict[str, Any],
    risk_level: Literal["low", "medium", "high"],
    requires_approval: bool = True,
    source_step_run_id: str | None = None,
    artifact_ids: list[str] | None = None,
    evidence_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Create a database-backed approval request for an action draft."""
    request = {
        "workflow_run_id": workflow_run_id,
        "action_type": action_type,
        "target": target,
        "payload": payload,
        "preview": preview,
        "risk_level": risk_level,
        "requires_approval": requires_approval,
        "source_step_run_id": source_step_run_id,
        "artifact_ids": artifact_ids or [],
        "evidence_ids": evidence_ids or [],
    }
    return await _call_provider(runtime, lambda context: resolve_knowledge_service_provider(runtime).approval_request(context, request))


@tool("approval_get")
async def approval_get(runtime: Runtime, approval_request_id: str) -> dict[str, Any]:
    """Get an approval request from the trusted workspace."""
    return await _call_provider(runtime, lambda context: resolve_knowledge_service_provider(runtime).approval_get(context, approval_request_id))


@tool("approval_decide")
async def approval_decide(runtime: Runtime, approval_request_id: str, decision: Literal["approve", "reject", "cancel"], reason: str | None = None) -> dict[str, Any]:
    """Approve, reject, or cancel an approval request using the trusted actor identity."""
    payload = {"approval_request_id": approval_request_id, "decision": decision, "reason": reason}
    return await _call_provider(runtime, lambda context: resolve_knowledge_service_provider(runtime).approval_decide(context, payload))


@tool("action_preview")
async def action_preview(runtime: Runtime, approval_request_id: str | None = None, action_draft: dict[str, Any] | None = None) -> dict[str, Any]:
    """Preview an action without external side effects."""
    payload = {"approval_request_id": approval_request_id, "action_draft": action_draft or {}}
    return await _call_provider(runtime, lambda context: resolve_knowledge_service_provider(runtime).action_preview(context, payload))


@tool("action_execute")
async def action_execute(runtime: Runtime, approval_request_id: str) -> dict[str, Any]:
    """Execute a database-approved action through the server-side adapter whitelist."""
    return await _call_provider(runtime, lambda context: resolve_knowledge_service_provider(runtime).action_execute(context, approval_request_id))


@tool("knowledge_artifact_validate")
async def knowledge_artifact_validate(runtime: Runtime, artifact_id: str) -> dict[str, Any]:
    """Validate artifact freshness, citations, and evidence links without mutation."""
    payload = {"artifact_id": artifact_id}
    return await _call_provider(runtime, lambda context: resolve_knowledge_service_provider(runtime).validate_artifact(context, payload))


@tool("knowledge_provenance_validate")
async def knowledge_provenance_validate(runtime: Runtime, citation_payload: dict[str, Any]) -> dict[str, Any]:
    """Validate citation and provenance references without mutation."""
    return await _call_provider(runtime, lambda context: resolve_knowledge_service_provider(runtime).validate_provenance(context, citation_payload))


@tool("workflow_validate")
async def workflow_validate(runtime: Runtime, workflow_run_id: str) -> dict[str, Any]:
    """Validate workflow completion conditions without mutation."""
    payload = {"workflow_run_id": workflow_run_id}
    return await _call_provider(runtime, lambda context: resolve_knowledge_service_provider(runtime).validate_workflow(context, payload))


@tool("approval_validate")
async def approval_validate(runtime: Runtime, approval_request_id: str) -> dict[str, Any]:
    """Validate approval and action executability without mutation."""
    payload = {"approval_request_id": approval_request_id}
    return await _call_provider(runtime, lambda context: resolve_knowledge_service_provider(runtime).validate_approval(context, payload))


KNOWLEDGE_TOOLS = [
    knowledge_ingest,
    knowledge_ingestion_status,
    knowledge_search,
    knowledge_analyze,
    knowledge_get_source,
    knowledge_get_revision,
    knowledge_get_claims,
    knowledge_expand_graph,
    knowledge_compare_revisions,
    knowledge_find_conflicts,
    knowledge_generate_update_report,
    workflow_create,
    workflow_get,
    workflow_advance,
    workflow_generate_artifact,
    approval_request,
    approval_get,
    approval_decide,
    action_preview,
    action_execute,
    knowledge_artifact_validate,
    knowledge_provenance_validate,
    workflow_validate,
    approval_validate,
]
