from __future__ import annotations

import asyncio
import os
import time
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
import yaml
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from deerflow.knowledge.jobs import KnowledgeJobService, KnowledgeJobWorker
from deerflow.knowledge.jobs.models import KnowledgeJobStatus, KnowledgeJobType
from deerflow.knowledge.jobs.repository import KnowledgeJobRepository, utc_now
from deerflow.knowledge.runtime.context import TrustedKnowledgeContext
from deerflow.runtime.user_context import DEFAULT_USER_ID

pytestmark = pytest.mark.skipif(
    not os.getenv("KNOWLEDGE_GATEWAY_JOB_TEST_DATABASE_URL"),
    reason="KNOWLEDGE_GATEWAY_JOB_TEST_DATABASE_URL is not set",
)


@pytest_asyncio.fixture()
async def live_session_factory():
    engine = create_async_engine(os.environ["KNOWLEDGE_GATEWAY_JOB_TEST_DATABASE_URL"])
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE knowledge_job_events, knowledge_jobs"))
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        async with engine.begin() as conn:
            await conn.execute(text("TRUNCATE knowledge_job_events, knowledge_jobs"))
        await engine.dispose()


@pytest.fixture()
def minimal_gateway_config(tmp_path: Path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    home_path = tmp_path / "home"
    config_path.write_text(
        yaml.safe_dump(
            {
                "config_version": 13,
                "log_level": "warning",
                "models": [],
                "sandbox": {"use": "deerflow.sandbox.local:LocalSandboxProvider", "allow_host_bash": False},
                "memory": {"token_counting": "char"},
                "database": {"backend": "memory"},
                "run_events": {"backend": "memory"},
                "skills": {"enabled": False},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("DEER_FLOW_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("DEER_FLOW_HOME", str(home_path))
    monkeypatch.delenv("DEER_FLOW_AUTH_DISABLED", raising=False)

    from deerflow.config.app_config import reset_app_config

    reset_app_config()
    try:
        yield config_path
    finally:
        reset_app_config()


def _context(workspace_id):
    return TrustedKnowledgeContext(
        user_id="live-user",
        workspace_id=workspace_id,
        thread_id="live-thread",
        actor_id="live-user",
        storage_root=Path("/nonexistent"),
    )


def _gateway_headers() -> dict[str, str]:
    from app.gateway.internal_auth import create_internal_auth_headers

    return {**create_internal_auth_headers(), "X-CSRF-Token": "csrf-token"}


def _gateway_client(app) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    client = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    client.cookies.set("csrf_token", "csrf-token")
    return client


async def _wait_for_status(client: httpx.AsyncClient, job_id: str, expected: set[str]) -> dict:
    deadline = asyncio.get_running_loop().time() + 10
    last = None
    while asyncio.get_running_loop().time() < deadline:
        response = await client.get(f"/api/knowledge/jobs/{job_id}", headers=_gateway_headers())
        assert response.status_code == 200
        last = response.json()
        if last["status"] in expected:
            return last
        await asyncio.sleep(0.1)
    raise AssertionError(f"job did not reach {sorted(expected)}; last={last}")


@pytest.mark.asyncio
async def test_live_postgres_job_claim_lease_recovery_retry_cancel_idempotency_and_events(live_session_factory) -> None:
    workspace_a = uuid4()
    workspace_b = uuid4()
    service = KnowledgeJobService(live_session_factory)

    job = await service.enqueue(
        workspace_id=workspace_a,
        job_type=KnowledgeJobType.ANALYZE,
        payload={"query": "q"},
        idempotency_key="same-active-job",
    )
    duplicate = await service.enqueue(
        workspace_id=workspace_a,
        job_type=KnowledgeJobType.ANALYZE,
        payload={"query": "q"},
        idempotency_key="same-active-job",
    )
    assert duplicate.id == job.id
    assert await service.get(workspace_b, job.id) is None
    assert await service.events(workspace_b, job.id) == []

    async with live_session_factory() as session:
        repo = KnowledgeJobRepository(session)
        first = await repo.claim_next(worker_id="worker-a", lease_ttl=timedelta(seconds=30), job_types=[KnowledgeJobType.ANALYZE])
        second = await repo.claim_next(worker_id="worker-b", lease_ttl=timedelta(seconds=30), job_types=[KnowledgeJobType.ANALYZE])
        await session.commit()
    assert first is not None
    assert first.id == job.id
    assert second is None

    async with live_session_factory() as session:
        row = await KnowledgeJobRepository(session).get(workspace_a, job.id)
        assert row is not None
        row.lease_expires_at = utc_now() - timedelta(seconds=1)
        await session.commit()

    async with live_session_factory() as session:
        recovered = await KnowledgeJobRepository(session).claim_next(
            worker_id="worker-b",
            lease_ttl=timedelta(seconds=30),
            job_types=[KnowledgeJobType.ANALYZE],
        )
        await session.commit()
    assert recovered is not None
    assert recovered.lease_owner == "worker-b"

    failing = await service.enqueue(workspace_id=workspace_a, job_type=KnowledgeJobType.INDEX, payload={"revision_id": str(uuid4())})

    async def fail_handler(context, claimed):
        raise RuntimeError("fake provider unavailable")

    retry_worker = KnowledgeJobWorker(session_factory=live_session_factory, handlers={KnowledgeJobType.INDEX: fail_handler}, worker_id="retry-worker")
    assert await retry_worker.run_once() is True
    failed_once = await service.get(workspace_a, failing.id)
    assert failed_once is not None
    assert failed_once.status == KnowledgeJobStatus.RETRY_SCHEDULED
    assert failed_once.attempt == 1
    assert failed_once.next_run_at > utc_now()
    assert failed_once.error_type == "RuntimeError"
    assert "Traceback" not in (failed_once.error_message or "")

    cancellable = await service.enqueue(workspace_id=workspace_a, job_type=KnowledgeJobType.WORKFLOW_ADVANCE, payload={"workflow_run_id": str(uuid4())})

    async def cancel_during_handler(context, claimed):
        await service.cancel(context.workspace_id, claimed.id)
        return {"workflow_run_id": claimed.payload["workflow_run_id"]}

    cancel_worker = KnowledgeJobWorker(
        session_factory=live_session_factory,
        handlers={KnowledgeJobType.WORKFLOW_ADVANCE: cancel_during_handler},
        worker_id="cancel-worker",
    )
    assert await cancel_worker.run_once() is True
    cancelled = await service.get(workspace_a, cancellable.id)
    assert cancelled is not None
    assert cancelled.status == KnowledgeJobStatus.CANCELLED

    succeeded = await service.enqueue(workspace_id=workspace_a, job_type=KnowledgeJobType.INGEST, payload={"source_type": "text", "source_uri": "small"})
    calls = 0

    async def success_handler(context, claimed):
        nonlocal calls
        calls += 1
        return {"resource_id": "ingestion-result"}

    success_worker = KnowledgeJobWorker(session_factory=live_session_factory, handlers={KnowledgeJobType.INGEST: success_handler}, worker_id="success-worker")
    assert await success_worker.run_once() is True
    assert await success_worker.run_once() is False
    assert calls == 1
    done = await service.get(workspace_a, succeeded.id)
    assert done is not None
    assert done.status == KnowledgeJobStatus.SUCCEEDED
    assert done.result_reference == {"resource_id": "ingestion-result"}

    events = await service.events(workspace_a, succeeded.id)
    assert [event.seq for event in events] == sorted(event.seq for event in events)
    assert [event.event_type for event in events] == ["job_queued", "job_started", "job_progress", "job_succeeded"]
    assert [event.event_type for event in await service.events(workspace_a, succeeded.id, after_seq=1)] == [
        "job_started",
        "job_progress",
        "job_succeeded",
    ]


@pytest.mark.asyncio
async def test_live_gateway_api_202_csrf_workspace_and_sse_cursor(live_session_factory, monkeypatch) -> None:
    from app.gateway.app import create_app
    from deerflow.knowledge.runtime.provider import UnconfiguredKnowledgeServiceProvider

    monkeypatch.delenv("DEER_FLOW_AUTH_DISABLED", raising=False)
    app = create_app()
    app.state.knowledge_provider = UnconfiguredKnowledgeServiceProvider()
    app.state.knowledge_job_service = KnowledgeJobService(live_session_factory)
    transport = httpx.ASGITransport(app=app)
    client = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    client.cookies.set("csrf_token", "csrf-token")

    missing_csrf = await client.post(
        "/api/knowledge/ingestions",
        json={"source_type": "text", "source_uri": "hello"},
        headers={k: v for k, v in _gateway_headers().items() if k != "X-CSRF-Token"},
    )
    assert missing_csrf.status_code == 403

    rejected = await client.post(
        "/api/knowledge/ingestions",
        json={"source_type": "text", "source_uri": "hello", "workspace_id": str(uuid4())},
        headers=_gateway_headers(),
    )
    assert rejected.status_code == 422

    response = await client.post("/api/knowledge/ingestions", json={"source_type": "text", "source_uri": "hello"}, headers=_gateway_headers())
    assert response.status_code == 202
    body = response.json()
    assert body["job_id"]
    assert body["status_url"].endswith(f"/api/knowledge/jobs/{body['job_id']}")
    assert body["events_url"].endswith(f"/api/knowledge/jobs/{body['job_id']}/events")

    status_response = await client.get(f"/api/knowledge/jobs/{body['job_id']}", headers=_gateway_headers())
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "QUEUED"

    from app.gateway.routers.knowledge import knowledge_job_events

    class _DisconnectableRequest:
        def __init__(self) -> None:
            self.app = SimpleNamespace(state=SimpleNamespace(knowledge_job_service=app.state.knowledge_job_service))
            self.state = SimpleNamespace(user=SimpleNamespace(id=DEFAULT_USER_ID))

        async def is_disconnected(self) -> bool:
            return False

    # Closing the SSE body iterator after the first event must not cancel the durable job.
    sse_request = _DisconnectableRequest()
    stream_response = await knowledge_job_events(UUID(body["job_id"]), sse_request, after_seq=None, limit=100)
    first_chunk = await anext(stream_response.body_iterator)
    await stream_response.body_iterator.aclose()
    assert first_chunk.startswith("id: 1\n")

    still_queued = await client.get(f"/api/knowledge/jobs/{body['job_id']}", headers=_gateway_headers())
    assert still_queued.json()["status"] == "QUEUED"

    retry = await client.post(f"/api/knowledge/ingestions/{body['job_id']}/retry", headers=_gateway_headers())
    assert retry.status_code == 202
    reconnect_response = await knowledge_job_events(UUID(body["job_id"]), sse_request, after_seq=1, limit=100)
    reconnect_chunk = await anext(reconnect_response.body_iterator)
    await reconnect_response.body_iterator.aclose()
    assert reconnect_chunk.startswith("id: 2\n")
    await client.aclose()


@pytest.mark.asyncio
async def test_formal_gateway_lifespan_starts_real_provider_worker_and_processes_ingestion(
    minimal_gateway_config: Path,
    monkeypatch,
) -> None:
    from alembic import command
    from alembic.config import Config

    from app.gateway.app import create_app
    from deerflow.knowledge.jobs.models import KnowledgeJob
    from deerflow.knowledge.runtime.provider import DatabaseKnowledgeServiceProvider

    database_url = os.environ["KNOWLEDGE_GATEWAY_JOB_TEST_DATABASE_URL"]
    script = Path.cwd() / "packages/harness/deerflow/persistence/migrations"
    cfg = Config(str(script / "alembic.ini"))
    cfg.set_main_option("script_location", str(script))
    cfg.set_main_option("sqlalchemy.url", database_url)
    await asyncio.to_thread(command.downgrade, cfg, "base")
    await asyncio.to_thread(command.upgrade, cfg, "head")

    monkeypatch.setenv("KNOWLEDGE_DATABASE_URL", database_url)
    monkeypatch.setenv("KNOWLEDGE_WORKER_ENABLED", "true")

    app = create_app()
    worker_task = None
    job_id = None
    async with app.router.lifespan_context(app):
        provider = app.state.knowledge_provider
        assert isinstance(provider, DatabaseKnowledgeServiceProvider)
        assert provider.database.session_factory is not None
        assert app.state.knowledge_job_service is not None
        assert app.state.knowledge_worker is not None
        assert app.state.knowledge_worker._task is not None
        assert not app.state.knowledge_worker._task.done()
        worker_task = app.state.knowledge_worker._task

        client = _gateway_client(app)
        try:
            create_response = await client.post(
                "/api/knowledge/ingestions",
                json={"source_type": "text", "source_uri": "formal lifespan note", "idempotency_key": "formal-lifespan"},
                headers=_gateway_headers(),
            )
            assert create_response.status_code == 202
            body = create_response.json()
            job_id = body["job_id"]
            assert body["status_url"].endswith(f"/api/knowledge/jobs/{job_id}")
            assert body["events_url"].endswith(f"/api/knowledge/jobs/{job_id}/events")

            terminal = await _wait_for_status(client, job_id, {"SUCCEEDED"})
            assert terminal["attempt"] == 1
            assert terminal["result_reference"]["source_id"]

        finally:
            await client.aclose()

        async with provider.database.session_factory() as session:
            job = await session.get(KnowledgeJob, UUID(job_id))
            assert job is not None
            assert job.status == KnowledgeJobStatus.SUCCEEDED
            assert str(job.payload["_trusted_user_id"]) == DEFAULT_USER_ID
            assert "_trusted_storage_root" in job.payload
            rows = (
                (
                    await session.execute(
                        text("SELECT event_type FROM knowledge_job_events WHERE job_id = :job_id ORDER BY seq"),
                        {"job_id": job_id},
                    )
                )
                .scalars()
                .all()
            )
            assert rows == ["job_queued", "job_started", "job_progress", "job_succeeded"]
            assert (await session.execute(text("SELECT COUNT(*) FROM knowledge_job_events WHERE job_id = :job_id"), {"job_id": job_id})).scalar_one() == 4

        shutdown_started_at = time.monotonic()

    assert worker_task is not None
    assert time.monotonic() - shutdown_started_at < 7
    assert worker_task.done()
    assert app.state.knowledge_provider.database.session_factory is None
    assert app.state.knowledge_provider.database.engine is None
    from deerflow.persistence.engine import get_engine, get_session_factory

    assert get_engine() is None
    assert get_session_factory() is None


@pytest.mark.asyncio
async def test_formal_gateway_lifespan_without_knowledge_db_starts_and_reports_unconfigured(
    minimal_gateway_config: Path,
    monkeypatch,
) -> None:
    from app.gateway.app import create_app
    from deerflow.knowledge.runtime.provider import UnconfiguredKnowledgeServiceProvider

    monkeypatch.delenv("KNOWLEDGE_DATABASE_URL", raising=False)
    monkeypatch.delenv("KNOWLEDGE_WORKER_ENABLED", raising=False)

    app = create_app()
    async with app.router.lifespan_context(app):
        assert isinstance(app.state.knowledge_provider, UnconfiguredKnowledgeServiceProvider)
        assert not hasattr(app.state, "knowledge_worker")
        client = _gateway_client(app)
        try:
            health = await client.get("/health")
            assert health.status_code == 200
            response = await client.post(
                "/api/knowledge/ingestions",
                json={"source_type": "text", "source_uri": "hello"},
                headers=_gateway_headers(),
            )
            assert response.status_code == 503
            assert response.json()["detail"]["error"]["code"] == "service_not_configured"
        finally:
            await client.aclose()
