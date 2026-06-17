from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from app.gateway.deps import get_knowledge_job_service, get_knowledge_provider, get_trusted_knowledge_context
from deerflow.knowledge.jobs.models import KnowledgeJobType
from deerflow.knowledge.jobs.service import event_to_dict, job_to_dict
from deerflow.knowledge.runtime.provider import KnowledgeServiceUnavailableError

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

MAX_PAGE_LIMIT = 100
TERMINAL_EVENT_TYPES = {"job_succeeded", "job_failed", "job_cancelled"}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IngestionCreateRequest(StrictModel):
    source_type: Literal["file", "url", "text"]
    source_uri: str = Field(min_length=1)
    media_type: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = Field(default=None, max_length=256)


class SearchRequest(StrictModel):
    query: str = Field(min_length=1)
    filters: dict[str, Any] = Field(default_factory=dict)
    context_budget: int = Field(default=4000, ge=1, le=12000)


class AnalysisCreateRequest(StrictModel):
    query: str = Field(min_length=1)
    filters: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = Field(default=None, max_length=256)


class WorkflowCreateRequest(StrictModel):
    workflow_type: str = Field(min_length=1, max_length=128)
    input: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = Field(default=None, max_length=256)


class ApprovalDecisionRequest(StrictModel):
    decision: Literal["approve", "reject", "cancel"]
    reason: str | None = None


class ActionPreviewRequest(StrictModel):
    action_draft: dict[str, Any] = Field(default_factory=dict)


def _limit(limit: int) -> int:
    return min(limit, MAX_PAGE_LIMIT)


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"error": {"code": code, "message": message}})


def _translate_error(exc: Exception) -> HTTPException:
    if isinstance(exc, KnowledgeServiceUnavailableError):
        return _error(503, "service_not_configured", str(exc))
    if isinstance(exc, ValueError):
        return _error(404, "not_found", "Knowledge resource was not found")
    return _error(500, "job_failed", "Knowledge service failed")


def _accepted(request: Request, job: Any) -> tuple[dict[str, Any], int]:
    status_url = str(request.url_for("knowledge_job_status", job_id=str(job.id)))
    events_url = str(request.url_for("knowledge_job_events", job_id=str(job.id)))
    return (
        {
            "job_id": str(job.id),
            "status": str(job.status),
            "status_url": status_url,
            "events_url": events_url,
        },
        status.HTTP_202_ACCEPTED,
    )


def _job_payload(context, payload: dict[str, Any]) -> dict[str, Any]:
    trusted = {
        "_trusted_user_id": context.user_id,
        "_trusted_actor_id": context.actor_id,
        "_trusted_thread_id": context.thread_id,
        "_trusted_storage_root": str(context.storage_root),
    }
    return {**payload, **trusted}


@router.post("/ingestions", status_code=status.HTTP_202_ACCEPTED)
async def create_ingestion(body: IngestionCreateRequest, request: Request, response: Response) -> dict[str, Any]:
    context = get_trusted_knowledge_context(request)
    service = get_knowledge_job_service(request)
    payload = _job_payload(context, body.model_dump(exclude={"idempotency_key"}))
    job = await service.enqueue(workspace_id=context.workspace_id, job_type=KnowledgeJobType.INGEST, payload=payload, idempotency_key=body.idempotency_key)
    data, code = _accepted(request, job)
    response.status_code = code
    return data


@router.get("/ingestions/{job_id}", name="knowledge_ingestion_status")
async def get_ingestion(job_id: UUID, request: Request) -> dict[str, Any]:
    return await knowledge_job_status(job_id, request)


@router.post("/ingestions/{job_id}/retry", status_code=status.HTTP_202_ACCEPTED)
async def retry_ingestion(job_id: UUID, request: Request, response: Response) -> dict[str, Any]:
    return await retry_job(job_id, request, response)


@router.post("/ingestions/{job_id}/cancel", status_code=status.HTTP_202_ACCEPTED)
async def cancel_ingestion(job_id: UUID, request: Request, response: Response) -> dict[str, Any]:
    return await cancel_job(job_id, request, response)


@router.get("/overview")
async def overview(request: Request) -> dict[str, Any]:
    try:
        return await get_knowledge_provider(request).overview(get_trusted_knowledge_context(request), {})  # type: ignore[attr-defined]
    except Exception as exc:
        raise _translate_error(exc) from exc


@router.get("/sources")
async def list_sources(request: Request, limit: int = Query(default=50, ge=1, le=MAX_PAGE_LIMIT), offset: int = Query(default=0, ge=0)) -> dict[str, Any]:
    context = get_trusted_knowledge_context(request)
    provider = get_knowledge_provider(request)
    try:
        return await provider.list_sources(context, {"limit": _limit(limit), "offset": offset})  # type: ignore[attr-defined]
    except Exception as exc:
        raise _translate_error(exc) from exc


@router.get("/sources/{source_id}")
async def get_source(source_id: str, request: Request) -> dict[str, Any]:
    try:
        return await get_knowledge_provider(request).get_source(get_trusted_knowledge_context(request), source_id)
    except Exception as exc:
        raise _translate_error(exc) from exc


@router.get("/sources/{source_id}/detail")
async def get_source_detail(source_id: str, request: Request) -> dict[str, Any]:
    try:
        return await get_knowledge_provider(request).get_source_detail(get_trusted_knowledge_context(request), source_id)  # type: ignore[attr-defined]
    except Exception as exc:
        raise _translate_error(exc) from exc


@router.get("/sources/{source_id}/revisions")
async def list_source_revisions(source_id: str, request: Request, limit: int = Query(default=50, ge=1, le=MAX_PAGE_LIMIT), offset: int = Query(default=0, ge=0)) -> dict[str, Any]:
    context = get_trusted_knowledge_context(request)
    try:
        return await get_knowledge_provider(request).list_source_revisions(context, {"source_id": source_id, "limit": _limit(limit), "offset": offset})  # type: ignore[attr-defined]
    except Exception as exc:
        raise _translate_error(exc) from exc


@router.get("/revisions/{revision_id}")
async def get_revision(revision_id: str, request: Request) -> dict[str, Any]:
    try:
        return await get_knowledge_provider(request).get_revision(get_trusted_knowledge_context(request), revision_id)
    except Exception as exc:
        raise _translate_error(exc) from exc


@router.get("/claims")
async def get_claims(request: Request, limit: int = Query(default=50, ge=1, le=MAX_PAGE_LIMIT), offset: int = Query(default=0, ge=0)) -> dict[str, Any]:
    try:
        return await get_knowledge_provider(request).get_claims(get_trusted_knowledge_context(request), {"limit": _limit(limit), "offset": offset})
    except Exception as exc:
        raise _translate_error(exc) from exc


@router.get("/conflicts")
async def get_conflicts(request: Request, limit: int = Query(default=50, ge=1, le=MAX_PAGE_LIMIT), offset: int = Query(default=0, ge=0)) -> dict[str, Any]:
    try:
        return await get_knowledge_provider(request).find_conflicts(get_trusted_knowledge_context(request), {"limit": _limit(limit), "offset": offset})
    except Exception as exc:
        raise _translate_error(exc) from exc


@router.post("/search")
async def search(body: SearchRequest, request: Request) -> dict[str, Any]:
    try:
        return await asyncio.wait_for(get_knowledge_provider(request).search(get_trusted_knowledge_context(request), body.model_dump()), timeout=15)
    except TimeoutError as exc:
        raise _error(503, "service_not_configured", "Knowledge search timed out") from exc
    except Exception as exc:
        raise _translate_error(exc) from exc


@router.post("/analyses", status_code=status.HTTP_202_ACCEPTED)
async def create_analysis(body: AnalysisCreateRequest, request: Request, response: Response) -> dict[str, Any]:
    context = get_trusted_knowledge_context(request)
    service = get_knowledge_job_service(request)
    payload = _job_payload(context, body.model_dump(exclude={"idempotency_key"}))
    job = await service.enqueue(workspace_id=context.workspace_id, job_type=KnowledgeJobType.ANALYZE, payload=payload, idempotency_key=body.idempotency_key)
    data, code = _accepted(request, job)
    response.status_code = code
    return data


@router.get("/analyses/{job_id}")
async def get_analysis(job_id: UUID, request: Request) -> dict[str, Any]:
    return await knowledge_job_status(job_id, request)


@router.get("/workflows")
async def list_workflows(request: Request, limit: int = Query(default=50, ge=1, le=MAX_PAGE_LIMIT), offset: int = Query(default=0, ge=0)) -> dict[str, Any]:
    try:
        return await get_knowledge_provider(request).list_workflows(get_trusted_knowledge_context(request), {"limit": _limit(limit), "offset": offset})  # type: ignore[attr-defined]
    except Exception as exc:
        raise _translate_error(exc) from exc


@router.post("/workflows", status_code=status.HTTP_202_ACCEPTED)
async def create_workflow(body: WorkflowCreateRequest, request: Request, response: Response) -> dict[str, Any]:
    context = get_trusted_knowledge_context(request)
    try:
        result = await get_knowledge_provider(request).workflow_create(context, body.model_dump())
        return result
    except KnowledgeServiceUnavailableError:
        payload = _job_payload(context, body.model_dump(exclude={"idempotency_key"}))
        job = await get_knowledge_job_service(request).enqueue(
            workspace_id=context.workspace_id,
            job_type=KnowledgeJobType.WORKFLOW_ADVANCE,
            payload=payload,
            idempotency_key=body.idempotency_key,
        )
        data, code = _accepted(request, job)
        response.status_code = code
        return data
    except Exception as exc:
        raise _translate_error(exc) from exc


@router.get("/workflows/{workflow_run_id}")
async def get_workflow(workflow_run_id: str, request: Request) -> dict[str, Any]:
    try:
        return await get_knowledge_provider(request).workflow_get(get_trusted_knowledge_context(request), workflow_run_id)
    except Exception as exc:
        raise _translate_error(exc) from exc


@router.post("/workflows/{workflow_run_id}/advance", status_code=status.HTTP_202_ACCEPTED)
async def advance_workflow(workflow_run_id: str, request: Request, response: Response) -> dict[str, Any]:
    context = get_trusted_knowledge_context(request)
    payload = _job_payload(context, {"workflow_run_id": workflow_run_id})
    job = await get_knowledge_job_service(request).enqueue(workspace_id=context.workspace_id, job_type=KnowledgeJobType.WORKFLOW_ADVANCE, payload=payload)
    data, code = _accepted(request, job)
    response.status_code = code
    return data


@router.post("/workflows/{workflow_run_id}/resume", status_code=status.HTTP_202_ACCEPTED)
async def resume_workflow(workflow_run_id: str, request: Request, response: Response) -> dict[str, Any]:
    return await advance_workflow(workflow_run_id, request, response)


@router.post("/workflows/{workflow_run_id}/retry", status_code=status.HTTP_202_ACCEPTED)
async def retry_workflow(workflow_run_id: UUID, request: Request, response: Response) -> dict[str, Any]:
    return await retry_job(workflow_run_id, request, response)


@router.get("/artifacts")
async def list_artifacts(request: Request, limit: int = Query(default=50, ge=1, le=MAX_PAGE_LIMIT), offset: int = Query(default=0, ge=0)) -> dict[str, Any]:
    try:
        return await get_knowledge_provider(request).list_artifacts(get_trusted_knowledge_context(request), {"limit": _limit(limit), "offset": offset})  # type: ignore[attr-defined]
    except Exception as exc:
        raise _translate_error(exc) from exc


@router.get("/artifacts/{artifact_id}")
async def get_artifact(artifact_id: str, request: Request) -> dict[str, Any]:
    try:
        return await get_knowledge_provider(request).get_artifact(get_trusted_knowledge_context(request), artifact_id)  # type: ignore[attr-defined]
    except Exception as exc:
        raise _translate_error(exc) from exc


@router.get("/approvals")
async def list_approvals(request: Request, limit: int = Query(default=50, ge=1, le=MAX_PAGE_LIMIT), offset: int = Query(default=0, ge=0)) -> dict[str, Any]:
    try:
        return await get_knowledge_provider(request).list_approvals(get_trusted_knowledge_context(request), {"limit": _limit(limit), "offset": offset})  # type: ignore[attr-defined]
    except Exception as exc:
        raise _translate_error(exc) from exc


@router.get("/approvals/{approval_id}")
async def get_approval(approval_id: str, request: Request) -> dict[str, Any]:
    try:
        return await get_knowledge_provider(request).approval_get(get_trusted_knowledge_context(request), approval_id)
    except Exception as exc:
        raise _translate_error(exc) from exc


@router.post("/approvals/{approval_id}/decision")
async def decide_approval(approval_id: str, body: ApprovalDecisionRequest, request: Request) -> dict[str, Any]:
    context = get_trusted_knowledge_context(request)
    payload = {**body.model_dump(), "approval_request_id": approval_id}
    try:
        return await get_knowledge_provider(request).approval_decide(context, payload)
    except Exception as exc:
        raise _translate_error(exc) from exc


@router.post("/actions/{approval_id}/preview")
async def preview_action(approval_id: str, body: ActionPreviewRequest, request: Request) -> dict[str, Any]:
    payload = {**body.model_dump(), "approval_request_id": approval_id}
    try:
        return await get_knowledge_provider(request).action_preview(get_trusted_knowledge_context(request), payload)
    except Exception as exc:
        raise _translate_error(exc) from exc


@router.post("/actions/{approval_id}/execute")
async def execute_action(approval_id: str, request: Request) -> dict[str, Any]:
    try:
        return await get_knowledge_provider(request).action_execute(get_trusted_knowledge_context(request), approval_id)
    except ValueError as exc:
        raise _error(409, "action_not_approved", "Action is not approved") from exc
    except Exception as exc:
        raise _translate_error(exc) from exc


@router.get("/jobs/{job_id}", name="knowledge_job_status")
async def knowledge_job_status(job_id: UUID, request: Request) -> dict[str, Any]:
    context = get_trusted_knowledge_context(request)
    job = await get_knowledge_job_service(request).get(context.workspace_id, job_id)
    if job is None:
        raise _error(404, "not_found", "Knowledge job was not found")
    return job_to_dict(job)


async def retry_job(job_id: UUID, request: Request, response: Response) -> dict[str, Any]:
    context = get_trusted_knowledge_context(request)
    job = await get_knowledge_job_service(request).retry(context.workspace_id, job_id)
    if job is None:
        raise _error(404, "not_found", "Knowledge job was not found")
    data, code = _accepted(request, job)
    response.status_code = code
    return data


async def cancel_job(job_id: UUID, request: Request, response: Response) -> dict[str, Any]:
    context = get_trusted_knowledge_context(request)
    job = await get_knowledge_job_service(request).cancel(context.workspace_id, job_id)
    if job is None:
        raise _error(404, "not_found", "Knowledge job was not found")
    data, code = _accepted(request, job)
    response.status_code = code
    return data


@router.get("/jobs/{job_id}/events", name="knowledge_job_events")
async def knowledge_job_events(
    job_id: UUID,
    request: Request,
    after_seq: int | None = Query(default=None, ge=0),
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
    limit: int = Query(default=100, ge=1, le=MAX_PAGE_LIMIT),
) -> StreamingResponse:
    context = get_trusted_knowledge_context(request)
    cursor = after_seq
    if cursor is None and last_event_id:
        try:
            cursor = int(last_event_id)
        except ValueError as exc:
            raise _error(400, "invalid_cursor", "Last-Event-ID must be an integer sequence") from exc

    async def stream() -> AsyncIterator[str]:
        nonlocal cursor
        while not await request.is_disconnected():
            events = await get_knowledge_job_service(request).events(context.workspace_id, job_id, after_seq=cursor, limit=_limit(limit))
            for event in events:
                cursor = event.seq
                yield f"id: {event.seq}\nevent: {event.event_type}\ndata: {json.dumps(event_to_dict(event), ensure_ascii=False)}\n\n"
                if event.event_type in TERMINAL_EVENT_TYPES:
                    return
            if events:
                continue
            yield ": heartbeat\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "Connection": "keep-alive"})


@router.get("/activity")
async def activity(request: Request, limit: int = Query(default=50, ge=1, le=MAX_PAGE_LIMIT), offset: int = Query(default=0, ge=0)) -> dict[str, Any]:
    context = get_trusted_knowledge_context(request)
    jobs = await get_knowledge_job_service(request).list(context.workspace_id, limit=_limit(limit), offset=offset)
    return {"data": [job_to_dict(job) for job in jobs], "pagination": {"limit": _limit(limit), "offset": offset}}
