from __future__ import annotations

import time
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.testclient import TestClient

from app.gateway.routers.knowledge import AnalysisCreateRequest, IngestionCreateRequest, KnowledgeUpdateReportRequest, RevisionCompareRequest
from deerflow.knowledge.jobs import KnowledgeJobService, KnowledgeJobWorker, NonRetryableKnowledgeJobError
from deerflow.knowledge.jobs.models import KnowledgeJob, KnowledgeJobEvent, KnowledgeJobStatus, KnowledgeJobType
from deerflow.knowledge.jobs.repository import KnowledgeJobRepository, utc_now


@pytest_asyncio.fixture()
async def job_session_factory(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'jobs.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(KnowledgeJob.__table__.create)
        await conn.run_sync(KnowledgeJobEvent.__table__.create)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


def test_ingestion_schema_rejects_client_trusted_fields() -> None:
    with pytest.raises(ValidationError):
        IngestionCreateRequest(
            source_type="file",
            source_uri="/mnt/user-data/thread/file.md",
            workspace_id=str(uuid4()),
            user_id="attacker",
            actor_id="attacker",
        )


def test_analysis_schema_rejects_client_trusted_fields() -> None:
    with pytest.raises(ValidationError):
        AnalysisCreateRequest(
            query="hello",
            workspace_id=str(uuid4()),
            user_id="attacker",
            actor_id="attacker",
        )


def test_revision_compare_schema_rejects_client_trusted_fields() -> None:
    with pytest.raises(ValidationError):
        RevisionCompareRequest(
            old_revision_id=uuid4(),
            new_revision_id=uuid4(),
            workspace_id=str(uuid4()),
        )


def test_update_report_schema_rejects_client_trusted_fields() -> None:
    with pytest.raises(ValidationError):
        KnowledgeUpdateReportRequest(
            old_revision_id=uuid4(),
            new_revision_id=uuid4(),
            user_id="attacker",
        )


def test_gateway_registers_knowledge_routes() -> None:
    from app.gateway.app import create_app

    paths = {route.path for route in create_app().routes}

    assert "/api/knowledge/ingestions" in paths
    assert "/api/knowledge/jobs/{job_id}" in paths
    assert "/api/knowledge/jobs/{job_id}/events" in paths
    assert "/api/knowledge/search" in paths
    assert "/api/knowledge/overview" in paths
    assert "/api/knowledge/sources/{source_id}/detail" in paths
    assert "/api/knowledge/revisions/compare" in paths
    assert "/api/knowledge/update-reports" in paths
    assert "/api/knowledge/conflicts/{conflict_group_id}" in paths
    assert "/api/knowledge/workflows" in paths


def _knowledge_headers() -> dict[str, str]:
    from app.gateway.internal_auth import create_internal_auth_headers

    return {**create_internal_auth_headers(owner_user_id="owner-a"), "X-CSRF-Token": "csrf-token"}


def _client_with_state(monkeypatch, *, job_service=None, provider=None) -> TestClient:
    from app.gateway.app import create_app
    from deerflow.knowledge.runtime.provider import UnconfiguredKnowledgeServiceProvider

    monkeypatch.delenv("DEER_FLOW_AUTH_DISABLED", raising=False)
    app = create_app()
    app.state.knowledge_provider = provider or UnconfiguredKnowledgeServiceProvider()
    if job_service is not None:
        app.state.knowledge_job_service = job_service
    client = TestClient(app)
    client.cookies.set("csrf_token", "csrf-token")
    return client


class _FakeGatewayJobService:
    def __init__(self) -> None:
        self.job_id = uuid4()
        self.seen_workspace_ids = []

    async def enqueue(self, *, workspace_id, job_type, payload, idempotency_key=None, max_attempts=3):
        self.seen_workspace_ids.append(workspace_id)
        assert "_trusted_user_id" in payload
        assert "workspace_id" not in payload
        return SimpleNamespace(id=self.job_id, status=KnowledgeJobStatus.QUEUED)

    async def get(self, workspace_id, job_id):
        return None

    async def list(self, workspace_id, *, limit, offset=0):
        return []

    async def events(self, workspace_id, job_id, *, after_seq=None, limit=100):
        return []


class _FakeGatewayProvider:
    async def overview(self, context, payload):
        return {"stats": {"sources": 1}, "recent_sources": [], "running_jobs": [], "recent_artifacts": [], "pending_approvals": []}

    async def list_sources(self, context, payload):
        return {"data": [], "pagination": {"limit": payload["limit"], "offset": payload["offset"]}}

    async def get_source_detail(self, context, source_id):
        return {"source": {"source_id": str(source_id)}, "revisions": [], "chunks": [], "claims": [], "relations": [], "evidence": [], "jobs": []}

    async def compare_revisions(self, context, payload):
        assert "workspace_id" not in payload
        return {"old_revision_id": payload["old_revision_id"], "new_revision_id": payload["new_revision_id"], "changes": []}

    async def generate_update_report(self, context, payload):
        assert "workspace_id" not in payload
        return {"status": "succeeded", "new_revision_id": payload["new_revision_id"], "conflict_groups": [], "stale_artifacts": []}

    async def find_conflicts(self, context, payload):
        return {"data": [], "pagination": {"limit": payload["limit"], "offset": payload["offset"]}}

    async def get_conflict(self, context, conflict_group_id):
        return {"conflict_group_id": str(conflict_group_id), "classification": "DIRECT_CONTRADICTION", "claims": []}

    async def list_workflows(self, context, payload):
        return {"data": [], "pagination": {"limit": payload["limit"], "offset": payload["offset"]}}

    async def action_execute(self, context, approval_request_id):
        raise ValueError("ApprovalRequest is not approved")

    async def analyze(self, context, payload):
        assert "workspace_id" not in payload
        assert "_trusted_user_id" not in payload
        return {"query": payload["query"], "model_identity": "fake-analysis"}


def test_gateway_create_analysis_returns_sync_result(monkeypatch) -> None:
    client = _client_with_state(monkeypatch, job_service=_FakeGatewayJobService(), provider=_FakeGatewayProvider())

    response = client.post(
        "/api/knowledge/analyses",
        json={"query": "hello", "context_budget": 500},
        headers=_knowledge_headers(),
    )

    assert response.status_code == 200
    assert response.json() == {"query": "hello", "model_identity": "fake-analysis"}


def test_gateway_create_ingestion_returns_202_and_trusted_urls(monkeypatch) -> None:
    service = _FakeGatewayJobService()
    client = _client_with_state(monkeypatch, job_service=service, provider=_FakeGatewayProvider())

    response = client.post(
        "/api/knowledge/ingestions",
        json={"source_type": "text", "source_uri": "hello", "idempotency_key": "idem"},
        headers=_knowledge_headers(),
    )

    assert response.status_code == 202
    body = response.json()
    assert body["job_id"] == str(service.job_id)
    assert body["status_url"].endswith(f"/api/knowledge/jobs/{service.job_id}")
    assert body["events_url"].endswith(f"/api/knowledge/jobs/{service.job_id}/events")


def test_gateway_mutating_endpoint_requires_csrf(monkeypatch) -> None:
    client = _client_with_state(monkeypatch, job_service=_FakeGatewayJobService(), provider=_FakeGatewayProvider())
    headers = _knowledge_headers()
    headers.pop("X-CSRF-Token")

    response = client.post("/api/knowledge/ingestions", json={"source_type": "text", "source_uri": "hello"}, headers=headers)

    assert response.status_code == 403
    assert response.json()["detail"] == "CSRF token missing. Include X-CSRF-Token header."


def test_gateway_schema_rejects_client_trusted_fields(monkeypatch) -> None:
    client = _client_with_state(monkeypatch, job_service=_FakeGatewayJobService(), provider=_FakeGatewayProvider())

    response = client.post(
        "/api/knowledge/ingestions",
        json={"source_type": "text", "source_uri": "hello", "workspace_id": str(uuid4())},
        headers=_knowledge_headers(),
    )

    assert response.status_code == 422


def test_gateway_list_endpoint_paginates_and_caps_limit(monkeypatch) -> None:
    client = _client_with_state(monkeypatch, job_service=_FakeGatewayJobService(), provider=_FakeGatewayProvider())

    response = client.get("/api/knowledge/sources?limit=100&offset=2", headers=_knowledge_headers())

    assert response.status_code == 200
    assert response.json()["pagination"] == {"limit": 100, "offset": 2}


def test_gateway_overview_uses_formal_provider_contract(monkeypatch) -> None:
    client = _client_with_state(monkeypatch, job_service=_FakeGatewayJobService(), provider=_FakeGatewayProvider())

    response = client.get("/api/knowledge/overview", headers=_knowledge_headers())

    assert response.status_code == 200
    assert response.json()["stats"] == {"sources": 1}


def test_gateway_source_detail_uses_formal_provider_contract(monkeypatch) -> None:
    client = _client_with_state(monkeypatch, job_service=_FakeGatewayJobService(), provider=_FakeGatewayProvider())
    source_id = uuid4()

    response = client.get(f"/api/knowledge/sources/{source_id}/detail", headers=_knowledge_headers())

    assert response.status_code == 200
    assert response.json()["source"]["source_id"] == str(source_id)
    assert response.json()["revisions"] == []


def test_gateway_revision_compare_uses_formal_provider_contract(monkeypatch) -> None:
    client = _client_with_state(monkeypatch, job_service=_FakeGatewayJobService(), provider=_FakeGatewayProvider())
    old_revision_id = uuid4()
    new_revision_id = uuid4()

    response = client.post(
        "/api/knowledge/revisions/compare",
        json={"old_revision_id": str(old_revision_id), "new_revision_id": str(new_revision_id)},
        headers=_knowledge_headers(),
    )

    assert response.status_code == 200
    assert response.json()["old_revision_id"] == str(old_revision_id)
    assert response.json()["new_revision_id"] == str(new_revision_id)


def test_gateway_update_report_uses_formal_provider_contract(monkeypatch) -> None:
    client = _client_with_state(monkeypatch, job_service=_FakeGatewayJobService(), provider=_FakeGatewayProvider())
    new_revision_id = uuid4()

    response = client.post(
        "/api/knowledge/update-reports",
        json={"new_revision_id": str(new_revision_id)},
        headers=_knowledge_headers(),
    )

    assert response.status_code == 200
    assert response.json()["new_revision_id"] == str(new_revision_id)
    assert response.json()["conflict_groups"] == []


def test_gateway_conflict_detail_uses_formal_provider_contract(monkeypatch) -> None:
    client = _client_with_state(monkeypatch, job_service=_FakeGatewayJobService(), provider=_FakeGatewayProvider())
    conflict_group_id = uuid4()

    response = client.get(f"/api/knowledge/conflicts/{conflict_group_id}", headers=_knowledge_headers())

    assert response.status_code == 200
    assert response.json()["conflict_group_id"] == str(conflict_group_id)
    assert response.json()["classification"] == "DIRECT_CONTRADICTION"


def test_gateway_workflow_list_paginates(monkeypatch) -> None:
    client = _client_with_state(monkeypatch, job_service=_FakeGatewayJobService(), provider=_FakeGatewayProvider())

    response = client.get("/api/knowledge/workflows?limit=20&offset=3", headers=_knowledge_headers())

    assert response.status_code == 200
    assert response.json()["pagination"] == {"limit": 20, "offset": 3}


def test_gateway_unconfigured_job_api_returns_structured_service_not_configured(monkeypatch) -> None:
    client = _client_with_state(monkeypatch)

    response = client.post("/api/knowledge/ingestions", json={"source_type": "text", "source_uri": "hello"}, headers=_knowledge_headers())

    assert response.status_code == 503
    assert response.json()["detail"]["error"]["code"] == "service_not_configured"


def test_gateway_unapproved_action_execute_is_rejected_by_domain_boundary(monkeypatch) -> None:
    client = _client_with_state(monkeypatch, job_service=_FakeGatewayJobService(), provider=_FakeGatewayProvider())

    response = client.post(f"/api/knowledge/actions/{uuid4()}/execute", headers=_knowledge_headers())

    assert response.status_code == 409
    assert response.json()["detail"]["error"]["code"] == "action_not_approved"


@pytest.mark.asyncio
async def test_job_service_idempotency_retry_cancel_and_events(job_session_factory) -> None:
    workspace_id = uuid4()
    service = KnowledgeJobService(job_session_factory)

    first = await service.enqueue(
        workspace_id=workspace_id,
        job_type=KnowledgeJobType.INGEST,
        payload={"source_type": "text", "source_uri": "note"},
        idempotency_key="same",
    )
    second = await service.enqueue(
        workspace_id=workspace_id,
        job_type=KnowledgeJobType.INGEST,
        payload={"source_type": "text", "source_uri": "note"},
        idempotency_key="same",
    )

    assert first.id == second.id
    assert first.status == KnowledgeJobStatus.QUEUED

    retried = await service.retry(workspace_id, first.id)
    assert retried is not None
    assert retried.status == KnowledgeJobStatus.RETRY_SCHEDULED

    cancelled = await service.cancel(workspace_id, first.id)
    assert cancelled is not None
    assert cancelled.status == KnowledgeJobStatus.CANCEL_REQUESTED

    events = await service.events(workspace_id, first.id)
    assert [event.event_type for event in events] == ["job_queued", "job_retry_scheduled", "job_cancel_requested"]


@pytest.mark.asyncio
async def test_job_service_idempotency_reuses_succeeded_job(job_session_factory) -> None:
    workspace_id = uuid4()
    service = KnowledgeJobService(job_session_factory)

    first = await service.enqueue(
        workspace_id=workspace_id,
        job_type=KnowledgeJobType.ANALYZE,
        payload={"query": "q"},
        idempotency_key="stable",
    )

    async def handler(context, claimed):
        return {"analysis_id": str(claimed.id)}

    worker = KnowledgeJobWorker(session_factory=job_session_factory, handlers={KnowledgeJobType.ANALYZE: handler})
    assert await worker.run_once() is True

    duplicate = await service.enqueue(
        workspace_id=workspace_id,
        job_type=KnowledgeJobType.ANALYZE,
        payload={"query": "q"},
        idempotency_key="stable",
    )
    other_workspace = await service.enqueue(
        workspace_id=uuid4(),
        job_type=KnowledgeJobType.ANALYZE,
        payload={"query": "q"},
        idempotency_key="stable",
    )

    assert duplicate.id == first.id
    assert duplicate.status == KnowledgeJobStatus.SUCCEEDED
    assert other_workspace.id != first.id


@pytest.mark.asyncio
async def test_two_workers_claim_one_job_once_and_recover_expired_lease(job_session_factory) -> None:
    workspace_id = uuid4()
    service = KnowledgeJobService(job_session_factory)
    job = await service.enqueue(workspace_id=workspace_id, job_type=KnowledgeJobType.ANALYZE, payload={"query": "q"})

    async with job_session_factory() as session:
        repo = KnowledgeJobRepository(session)
        first = await repo.claim_next(worker_id="worker-a", lease_ttl=timedelta(seconds=30), job_types=[KnowledgeJobType.ANALYZE])
        second = await repo.claim_next(worker_id="worker-b", lease_ttl=timedelta(seconds=30), job_types=[KnowledgeJobType.ANALYZE])
        await session.commit()

    assert first is not None
    assert first.id == job.id
    assert second is None

    async with job_session_factory() as session:
        row = await KnowledgeJobRepository(session).get(workspace_id, job.id)
        assert row is not None
        row.lease_expires_at = utc_now() - timedelta(seconds=1)
        await session.commit()

    async with job_session_factory() as session:
        recovered = await KnowledgeJobRepository(session).claim_next(
            worker_id="worker-b",
            lease_ttl=timedelta(seconds=30),
            job_types=[KnowledgeJobType.ANALYZE],
        )
        await session.commit()

    assert recovered is not None
    assert recovered.id == job.id
    assert recovered.lease_owner == "worker-b"


@pytest.mark.asyncio
async def test_worker_uses_fake_handler_and_records_success(job_session_factory) -> None:
    workspace_id = uuid4()
    service = KnowledgeJobService(job_session_factory)
    job = await service.enqueue(workspace_id=workspace_id, job_type=KnowledgeJobType.ANALYZE, payload={"query": "q"})

    async def handler(context, claimed):
        assert context.workspace_id == workspace_id
        assert claimed.id == job.id
        return {"analysis_id": "fake-analysis"}

    worker = KnowledgeJobWorker(
        session_factory=job_session_factory,
        handlers={KnowledgeJobType.ANALYZE: handler},
        worker_id="worker-test",
    )

    assert await worker.run_once() is True
    updated = await service.get(workspace_id, job.id)
    assert updated is not None
    assert updated.status == KnowledgeJobStatus.SUCCEEDED
    assert updated.result_reference == {"analysis_id": "fake-analysis"}

    events = await service.events(workspace_id, job.id)
    assert [event.event_type for event in events] == ["job_queued", "job_started", "job_progress", "job_succeeded"]


@pytest.mark.asyncio
async def test_worker_non_retryable_error_enters_final_failure(job_session_factory) -> None:
    workspace_id = uuid4()
    service = KnowledgeJobService(job_session_factory)
    job = await service.enqueue(workspace_id=workspace_id, job_type=KnowledgeJobType.ANALYZE, payload={"query": "q"})

    async def handler(context, claimed):
        raise NonRetryableKnowledgeJobError("invalid request")

    worker = KnowledgeJobWorker(
        session_factory=job_session_factory,
        handlers={KnowledgeJobType.ANALYZE: handler},
        worker_id="worker-test",
    )

    assert await worker.run_once() is True
    updated = await service.get(workspace_id, job.id)
    assert updated is not None
    assert updated.status == KnowledgeJobStatus.FAILED
    assert updated.attempt == 1
    assert updated.error_type == "NonRetryableKnowledgeJobError"

    events = await service.events(workspace_id, job.id)
    assert [event.event_type for event in events] == ["job_queued", "job_started", "job_progress", "job_failed"]


@pytest.mark.asyncio
async def test_worker_shutdown_is_bounded(job_session_factory) -> None:
    worker = KnowledgeJobWorker(
        session_factory=job_session_factory,
        handlers={},
        poll_interval_seconds=30,
        shutdown_timeout_seconds=0.5,
    )

    await worker.start()
    started_at = time.monotonic()
    await worker.shutdown()

    assert time.monotonic() - started_at < 2


def test_gateway_request_context_derives_workspace_from_user() -> None:
    from app.gateway.deps import get_trusted_knowledge_context

    user = SimpleNamespace(id="user-a")
    request = SimpleNamespace(state=SimpleNamespace(user=user))

    first = get_trusted_knowledge_context(request)
    second = get_trusted_knowledge_context(request)

    assert first.user_id == "user-a"
    assert first.actor_id == "user-a"
    assert first.workspace_id == second.workspace_id


@pytest.mark.asyncio
async def test_gateway_sse_uses_last_event_id_and_stops_after_terminal_event(monkeypatch) -> None:
    from app.gateway.routers.knowledge import knowledge_job_events
    from deerflow.runtime.user_context import DEFAULT_USER_ID

    job_id = uuid4()
    seen_after_seq: list[int | None] = []

    class _FakeEventService:
        async def events(self, workspace_id, requested_job_id, *, after_seq=None, limit=100):
            seen_after_seq.append(after_seq)
            assert requested_job_id == job_id
            return [
                SimpleNamespace(
                    id=uuid4(),
                    job_id=str(job_id),
                    seq=3,
                    event_type="job_succeeded",
                    payload={},
                    created_at=utc_now(),
                )
            ]

    async def is_connected() -> bool:
        return False

    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(knowledge_job_service=_FakeEventService())),
        state=SimpleNamespace(user=SimpleNamespace(id=DEFAULT_USER_ID)),
        is_disconnected=is_connected,
    )

    response = await knowledge_job_events(job_id, request, after_seq=None, last_event_id="2", limit=100)
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk)

    assert seen_after_seq == [2]
    assert len(chunks) == 1
    assert chunks[0].startswith("id: 3\nevent: job_succeeded\n")


@pytest.mark.asyncio
async def test_gateway_sse_heartbeat_does_not_advance_cursor(monkeypatch) -> None:
    from app.gateway.routers.knowledge import knowledge_job_events
    from deerflow.runtime.user_context import DEFAULT_USER_ID

    job_id = uuid4()
    seen_after_seq: list[int | None] = []

    class _FakeEventService:
        async def events(self, workspace_id, requested_job_id, *, after_seq=None, limit=100):
            seen_after_seq.append(after_seq)
            return []

    class _Request:
        def __init__(self) -> None:
            self.app = SimpleNamespace(state=SimpleNamespace(knowledge_job_service=_FakeEventService()))
            self.state = SimpleNamespace(user=SimpleNamespace(id=DEFAULT_USER_ID))
            self.calls = 0

        async def is_disconnected(self) -> bool:
            self.calls += 1
            return self.calls > 1

    request = _Request()
    response = await knowledge_job_events(job_id, request, after_seq=4, last_event_id=None, limit=100)
    first_chunk = await anext(response.body_iterator)
    await response.body_iterator.aclose()

    assert first_chunk == ": heartbeat\n\n"
    assert seen_after_seq == [4]
