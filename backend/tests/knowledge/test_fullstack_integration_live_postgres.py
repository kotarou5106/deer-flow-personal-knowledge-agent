from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
import yaml
from alembic import command
from alembic.config import Config
from sqlalchemy import select, text

from deerflow.knowledge.enums import ArtifactStalenessStatus, ArtifactValidationStatus, WorkflowStatus
from deerflow.knowledge.models import Artifact, ArtifactEvidenceLink, Chunk, Claim, ClaimEvidenceLink, DocumentRevision, EvidenceSpan, Source, SourceSnapshot, WorkflowRun, WorkflowStepRun

pytestmark = pytest.mark.skipif(
    not os.getenv("KNOWLEDGE_FULLSTACK_TEST_DATABASE_URL"),
    reason="KNOWLEDGE_FULLSTACK_TEST_DATABASE_URL is not set",
)


@pytest.fixture()
def fullstack_gateway_config(tmp_path: Path, monkeypatch):
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
    monkeypatch.setenv("KNOWLEDGE_DATABASE_URL", os.environ["KNOWLEDGE_FULLSTACK_TEST_DATABASE_URL"])
    monkeypatch.setenv("KNOWLEDGE_WORKER_ENABLED", "true")
    monkeypatch.delenv("DEER_FLOW_AUTH_DISABLED", raising=False)

    from deerflow.config import paths as paths_module
    from deerflow.config.app_config import reset_app_config

    reset_app_config()
    monkeypatch.setattr(paths_module, "_paths", None)
    try:
        yield config_path
    finally:
        reset_app_config()
        monkeypatch.setattr(paths_module, "_paths", None)


@pytest_asyncio.fixture()
async def migrated_knowledge_db():
    database_url = os.environ["KNOWLEDGE_FULLSTACK_TEST_DATABASE_URL"]
    script = Path.cwd() / "packages/harness/deerflow/persistence/migrations"
    cfg = Config(str(script / "alembic.ini"))
    cfg.set_main_option("script_location", str(script))
    cfg.set_main_option("sqlalchemy.url", database_url)
    await asyncio.to_thread(command.downgrade, cfg, "base")
    await asyncio.to_thread(command.upgrade, cfg, "head")
    yield
    await asyncio.to_thread(command.downgrade, cfg, "base")


def _headers(user_id: str = "owner-a") -> dict[str, str]:
    from app.gateway.internal_auth import create_internal_auth_headers

    return {**create_internal_auth_headers(owner_user_id=user_id), "X-CSRF-Token": "csrf-token"}


def _client(app) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    client = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    client.cookies.set("csrf_token", "csrf-token")
    return client


async def _wait_for_status(client: httpx.AsyncClient, job_id: str, expected: set[str], *, user_id: str = "owner-a") -> dict:
    deadline = asyncio.get_running_loop().time() + 10
    last = None
    while asyncio.get_running_loop().time() < deadline:
        response = await client.get(f"/api/knowledge/jobs/{job_id}", headers=_headers(user_id))
        assert response.status_code == 200
        last = response.json()
        if last["status"] in expected:
            return last
        await asyncio.sleep(0.1)
    raise AssertionError(f"job did not reach {sorted(expected)}; last={last}")


async def _ingest_file(
    client: httpx.AsyncClient,
    *,
    source_uri: str,
    media_type: str,
    idempotency_key: str,
    user_id: str = "owner-a",
) -> dict:
    accepted = await client.post(
        "/api/knowledge/ingestions",
        json={
            "source_type": "file",
            "source_uri": source_uri,
            "media_type": media_type,
            "idempotency_key": idempotency_key,
        },
        headers=_headers(user_id),
    )
    assert accepted.status_code == 202
    terminal = await _wait_for_status(client, accepted.json()["job_id"], {"SUCCEEDED", "FAILED"}, user_id=user_id)
    assert terminal["status"] == "SUCCEEDED", terminal
    return terminal


async def _chunk_by_id(app, chunk_id: str) -> Chunk:
    async with app.state.knowledge_provider.database.session_factory() as session:
        chunk = await session.get(Chunk, chunk_id)
        assert chunk is not None
        return chunk


async def _claim_for_revision_text(app, revision_id: str, text_fragment: str) -> Claim:
    async with app.state.knowledge_provider.database.session_factory() as session:
        claim = (
            (
                await session.execute(
                    select(Claim)
                    .join(ClaimEvidenceLink, ClaimEvidenceLink.claim_id == Claim.id)
                    .join(EvidenceSpan, EvidenceSpan.id == ClaimEvidenceLink.evidence_span_id)
                    .join(Chunk, Chunk.id == EvidenceSpan.chunk_id)
                    .where(Chunk.revision_id == revision_id, Claim.claim_text.contains(text_fragment))
                )
            )
            .scalars()
            .first()
        )
        assert claim is not None
        return claim


async def _create_artifact_for_claim(app, claim: Claim) -> str:
    async with app.state.knowledge_provider.database.session_factory() as session:
        artifact = Artifact(
            workspace_id=claim.workspace_id,
            artifact_type="knowledge_update_review",
            title="Project update brief",
            storage_path="/tmp/project-update.md",
            validation_status=ArtifactValidationStatus.VALID,
            staleness_status=ArtifactStalenessStatus.FRESH,
            metadata_json={"markdown": "# Project update brief"},
        )
        session.add(artifact)
        await session.flush()
        session.add(
            ArtifactEvidenceLink(
                workspace_id=claim.workspace_id,
                artifact_id=artifact.id,
                claim_id=claim.id,
                usage_type="supports",
            )
        )
        await session.commit()
        return str(artifact.id)


async def _mark_first_workflow_step_failed(app, workflow_run_id: str) -> None:
    async with app.state.knowledge_provider.database.session_factory() as session:
        run = await session.get(WorkflowRun, workflow_run_id)
        assert run is not None
        step = (await session.execute(select(WorkflowStepRun).where(WorkflowStepRun.workspace_id == run.workspace_id, WorkflowStepRun.workflow_run_id == run.id).order_by(WorkflowStepRun.sequence).limit(1))).scalar_one()
        run.status = WorkflowStatus.FAILED
        run.error = "planned retry fixture"
        step.status = WorkflowStatus.FAILED
        step.error_type = "RuntimeError"
        step.error_message = "planned retry fixture"
        await session.commit()


async def _read_sse_until_terminal(client: httpx.AsyncClient, job_id: str, *, user_id: str = "owner-a") -> list[tuple[int, str]]:
    events: list[tuple[int, str]] = []
    async with client.stream("GET", f"/api/knowledge/jobs/{job_id}/events", headers=_headers(user_id), timeout=10) as response:
        assert response.status_code == 200
        current_id: int | None = None
        current_event: str | None = None
        async for line in response.aiter_lines():
            if line.startswith("id: "):
                current_id = int(line.removeprefix("id: "))
            elif line.startswith("event: "):
                current_event = line.removeprefix("event: ")
            elif line == "" and current_id is not None and current_event is not None:
                events.append((current_id, current_event))
                if current_event in {"job_succeeded", "job_failed", "job_cancelled"}:
                    break
                current_id = None
                current_event = None
    return events


async def _local_http_server(body: bytes, media_type: str = "text/html") -> AsyncIterator[str]:
    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await reader.read(4096)
        writer.write(b"HTTP/1.1 200 OK\r\n" + f"Content-Type: {media_type}\r\n".encode() + f"Content-Length: {len(body)}\r\n".encode() + b"Connection: close\r\n\r\n" + body)
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        yield f"http://127.0.0.1:{port}/fixture.html"
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_file_ingestion_sse_source_detail_search_and_workspace_isolation(fullstack_gateway_config, migrated_knowledge_db) -> None:
    from app.gateway.app import create_app
    from deerflow.config.paths import get_paths

    app = create_app()
    async with app.router.lifespan_context(app):
        owner_id = "owner-a"
        thread_id = owner_id
        paths = get_paths()
        paths.ensure_thread_dirs(thread_id, user_id=owner_id)
        upload_dir = paths.sandbox_uploads_dir(thread_id, user_id=owner_id)
        txt_path = upload_dir / "knowledge-live.txt"
        md_path = upload_dir / "knowledge-live.md"
        txt_path.write_text("Alpha knowledge launch budget includes deterministic retrieval evidence.", encoding="utf-8")
        md_path.write_text("# Launch Notes\n\nBeta markdown evidence mentions Sierra revenue planning.", encoding="utf-8")

        client = _client(app)
        try:
            first = await client.post(
                "/api/knowledge/ingestions",
                json={
                    "source_type": "file",
                    "source_uri": "/mnt/user-data/uploads/knowledge-live.txt",
                    "media_type": "text/plain",
                    "idempotency_key": "file-txt-once",
                },
                headers=_headers(owner_id),
            )
            assert first.status_code == 202
            first_body = first.json()
            forbidden = {"workspace_id", "user_id", "thread_id", "actor_id"}
            async with app.state.knowledge_provider.database.session_factory() as session:
                payload = (await session.execute(text("SELECT payload FROM knowledge_jobs WHERE id = :job_id"), {"job_id": first_body["job_id"]})).scalar_one()
            assert not (forbidden & set(payload))
            assert {"_trusted_user_id", "_trusted_thread_id", "_trusted_storage_root"} <= set(payload)

            events = await _read_sse_until_terminal(client, first_body["job_id"], user_id=owner_id)
            assert [seq for seq, _ in events] == sorted(seq for seq, _ in events)
            terminal = await _wait_for_status(client, first_body["job_id"], {"SUCCEEDED", "FAILED"}, user_id=owner_id)
            assert terminal["status"] == "SUCCEEDED", terminal
            assert [event for _, event in events] == ["job_queued", "job_started", "job_progress", "job_succeeded"]
            source_id = terminal["result_reference"]["source_id"]

            duplicate = await client.post(
                "/api/knowledge/ingestions",
                json={
                    "source_type": "file",
                    "source_uri": "/mnt/user-data/uploads/knowledge-live.txt",
                    "media_type": "text/plain",
                    "idempotency_key": "file-txt-once",
                },
                headers=_headers(owner_id),
            )
            assert duplicate.status_code == 202
            assert duplicate.json()["job_id"] == first_body["job_id"]

            markdown = await client.post(
                "/api/knowledge/ingestions",
                json={
                    "source_type": "file",
                    "source_uri": "/mnt/user-data/uploads/knowledge-live.md",
                    "media_type": "text/markdown",
                    "idempotency_key": "file-md-once",
                },
                headers=_headers(owner_id),
            )
            assert markdown.status_code == 202
            await _wait_for_status(client, markdown.json()["job_id"], {"SUCCEEDED"}, user_id=owner_id)

            sources = await client.get("/api/knowledge/sources", headers=_headers(owner_id))
            assert sources.status_code == 200
            assert len(sources.json()["data"]) == 2
            overview = await client.get("/api/knowledge/overview", headers=_headers(owner_id))
            assert overview.status_code == 200
            assert overview.json()["stats"]["sources"] == 2

            detail = await client.get(f"/api/knowledge/sources/{source_id}/detail", headers=_headers(owner_id))
            assert detail.status_code == 200
            detail_body = detail.json()
            assert detail_body["source"]["source_id"] == source_id
            assert detail_body["revisions"]
            assert detail_body["chunks"]

            search = await client.post("/api/knowledge/search", json={"query": "Alpha deterministic retrieval", "context_budget": 4000}, headers=_headers(owner_id))
            assert search.status_code == 200
            search_body = search.json()
            assert search_body["retrieved_chunks"]
            retrieved = search_body["retrieved_chunks"][0]
            assert retrieved["source_id"] == source_id
            assert "deterministic retrieval" in retrieved["content"]
            assert retrieved["provenance"]["chunk_id"]
            assert retrieved["provenance"]["start_offset"] == 0

            isolated = await client.get("/api/knowledge/sources", headers=_headers("owner-b"))
            assert isolated.status_code == 200
            assert isolated.json()["data"] == []

            async with app.state.knowledge_provider.database.session_factory() as session:
                assert (await session.execute(select(Source))).scalars().all()
                assert (await session.execute(select(SourceSnapshot))).scalars().all()
                assert (await session.execute(select(DocumentRevision))).scalars().all()
                assert (await session.execute(select(Chunk))).scalars().all()
        finally:
            await client.aclose()


@pytest.mark.asyncio
async def test_url_ingestion_ssrf_rejection_and_sse_reconnect(fullstack_gateway_config, migrated_knowledge_db, monkeypatch) -> None:
    import deerflow.knowledge.ingestion.acquisition as acquisition
    from app.gateway.app import create_app

    async def allow_localhost_for_test(url: str) -> None:
        return None

    app = create_app()
    async with app.router.lifespan_context(app):
        client = _client(app)
        try:
            cancellable = await client.post(
                "/api/knowledge/ingestions",
                json={"source_type": "url", "source_uri": "https://example.invalid/cancel-me", "idempotency_key": "cancel-me"},
                headers=_headers(),
            )
            assert cancellable.status_code == 202
            cancelled = await client.post(f"/api/knowledge/ingestions/{cancellable.json()['job_id']}/cancel", headers=_headers())
            assert cancelled.status_code == 202
            cancelled_status = await client.get(f"/api/knowledge/jobs/{cancellable.json()['job_id']}", headers=_headers())
            assert cancelled_status.status_code == 200
            assert cancelled_status.json()["status"] == "CANCEL_REQUESTED"

            blocked = await client.post(
                "/api/knowledge/ingestions",
                json={"source_type": "url", "source_uri": "http://127.0.0.1/private", "idempotency_key": "blocked-local-url"},
                headers=_headers(),
            )
            assert blocked.status_code == 202
            blocked_terminal = await _wait_for_status(client, blocked.json()["job_id"], {"FAILED"})
            assert blocked_terminal["error_type"] in {"SSRFBlockedError", "AcquisitionError"}

            monkeypatch.setattr(acquisition, "assert_safe_http_url", allow_localhost_for_test)
            async for url in _local_http_server(b"<html><title>Local Fixture</title><h1>Fixture</h1><p>Gamma URL ingestion evidence is searchable.</p></html>"):
                accepted = await client.post(
                    "/api/knowledge/ingestions",
                    json={"source_type": "url", "source_uri": url, "idempotency_key": "allowed-local-url"},
                    headers=_headers(),
                )
                assert accepted.status_code == 202
                job_id = accepted.json()["job_id"]
                first_stream = await client.get(f"/api/knowledge/jobs/{job_id}/events?limit=1", headers=_headers())
                assert first_stream.status_code == 200
                assert "id: 1" in first_stream.text
                reconnected = await client.get(f"/api/knowledge/jobs/{job_id}/events?after_seq=1&limit=10", headers=_headers(), timeout=10)
                assert reconnected.status_code == 200
                assert "id: 1" not in reconnected.text
                terminal = await _wait_for_status(client, job_id, {"SUCCEEDED"})
                source_id = terminal["result_reference"]["source_id"]
                detail = await client.get(f"/api/knowledge/sources/{source_id}/detail", headers=_headers())
                assert detail.status_code == 200
                assert "Gamma URL ingestion evidence" in detail.text
                search = await client.post("/api/knowledge/search", json={"query": "Gamma searchable", "context_budget": 4000}, headers=_headers())
                assert search.status_code == 200
                assert search.json()["retrieved_chunks"]
                break
        finally:
            await client.aclose()


@pytest.mark.asyncio
async def test_revision_update_conflict_report_and_stale_artifact_fullstack(fullstack_gateway_config, migrated_knowledge_db) -> None:
    from app.gateway.app import create_app
    from deerflow.config.paths import get_paths

    app = create_app()
    async with app.router.lifespan_context(app):
        owner_id = "revision-owner"
        paths = get_paths()
        paths.ensure_thread_dirs(owner_id, user_id=owner_id)
        upload_dir = paths.sandbox_uploads_dir(owner_id, user_id=owner_id)
        source_path = upload_dir / "project-status.txt"
        second_source_path = upload_dir / "external-status.txt"

        client = _client(app)
        try:
            source_path.write_text("Project deadline is June 20. Project model is v1.", encoding="utf-8")
            v1 = await _ingest_file(
                client,
                source_uri="/mnt/user-data/uploads/project-status.txt",
                media_type="text/plain",
                idempotency_key="project-status-v1",
                user_id=owner_id,
            )
            initial_report = await client.post(
                "/api/knowledge/update-reports",
                json={"new_revision_id": v1["result_reference"]["revision_id"]},
                headers=_headers(owner_id),
            )
            assert initial_report.status_code == 200
            assert "no previous revision" in initial_report.json()["message"].lower()

            old_deadline = await _claim_for_revision_text(app, v1["result_reference"]["revision_id"], "Project deadline")
            artifact_id = await _create_artifact_for_claim(app, old_deadline)

            source_path.write_text("Project deadline is June 25. Project model is v2. Project risk is high.", encoding="utf-8")
            v2 = await _ingest_file(
                client,
                source_uri="/mnt/user-data/uploads/project-status.txt",
                media_type="text/plain",
                idempotency_key="project-status-v2",
                user_id=owner_id,
            )
            assert v2["result_reference"]["source_id"] == v1["result_reference"]["source_id"]

            compare = await client.post(
                "/api/knowledge/revisions/compare",
                json={
                    "old_revision_id": v1["result_reference"]["revision_id"],
                    "new_revision_id": v2["result_reference"]["revision_id"],
                },
                headers=_headers(owner_id),
            )
            assert compare.status_code == 200
            compare_body = compare.json()
            assert compare_body["summary"]["modified"] >= 1
            assert "MODIFIED" in {item["change_type"] for item in compare_body["changes"]}
            assert compare_body["incremental_plan"]["reprocess_chunk_ids"]

            report = await client.post(
                "/api/knowledge/update-reports",
                json={
                    "old_revision_id": v1["result_reference"]["revision_id"],
                    "new_revision_id": v2["result_reference"]["revision_id"],
                },
                headers=_headers(owner_id),
            )
            assert report.status_code == 200
            report_body = report.json()
            assert report_body["status"] == "succeeded"
            assert report_body["new_claims"]
            assert report_body["conflict_groups"]
            assert any(item["artifact_id"] == artifact_id for item in report_body["stale_artifacts"])
            assert "Knowledge Update Report" in report_body["markdown"]
            assert "Conflict groups" in report_body["markdown"]

            source_path.write_text("Project deadline is not June 25. Project model is v3.", encoding="utf-8")
            v3 = await _ingest_file(
                client,
                source_uri="/mnt/user-data/uploads/project-status.txt",
                media_type="text/plain",
                idempotency_key="project-status-v3",
                user_id=owner_id,
            )
            direct = await client.post(
                "/api/knowledge/update-reports",
                json={
                    "old_revision_id": v2["result_reference"]["revision_id"],
                    "new_revision_id": v3["result_reference"]["revision_id"],
                },
                headers=_headers(owner_id),
            )
            assert direct.status_code == 200

            second_source_path.write_text("Project risk is medium.", encoding="utf-8")
            other_v1 = await _ingest_file(
                client,
                source_uri="/mnt/user-data/uploads/external-status.txt",
                media_type="text/plain",
                idempotency_key="external-status-v1",
                user_id=owner_id,
            )
            await client.post(
                "/api/knowledge/update-reports",
                json={"new_revision_id": other_v1["result_reference"]["revision_id"]},
                headers=_headers(owner_id),
            )
            second_source_path.write_text("Project deadline is July 01. Project model is not v3.", encoding="utf-8")
            other_v2 = await _ingest_file(
                client,
                source_uri="/mnt/user-data/uploads/external-status.txt",
                media_type="text/plain",
                idempotency_key="external-status-v2",
                user_id=owner_id,
            )
            disagreement = await client.post(
                "/api/knowledge/update-reports",
                json={
                    "old_revision_id": other_v1["result_reference"]["revision_id"],
                    "new_revision_id": other_v2["result_reference"]["revision_id"],
                },
                headers=_headers(owner_id),
            )
            assert disagreement.status_code == 200

            conflicts = await client.get("/api/knowledge/conflicts?limit=100", headers=_headers(owner_id))
            assert conflicts.status_code == 200
            conflict_rows = conflicts.json()["data"]
            classifications = {row["classification"] for row in conflict_rows}
            assert "TEMPORAL_UPDATE" in classifications
            assert "DIRECT_CONTRADICTION" in classifications
            assert "SOURCE_DISAGREEMENT" in classifications

            detail = await client.get(f"/api/knowledge/conflicts/{conflict_rows[0]['conflict_group_id']}", headers=_headers(owner_id))
            assert detail.status_code == 200
            detail_body = detail.json()
            assert detail_body["claims"]
            assert detail_body["citation_ids"]
            assert detail_body["recommended_next_step"]

            artifacts = await client.get("/api/knowledge/artifacts", headers=_headers(owner_id))
            assert artifacts.status_code == 200
            artifact = next(item for item in artifacts.json()["data"] if item["artifact_id"] == artifact_id)
            assert artifact["staleness_status"] == "stale"

            isolated = await client.get("/api/knowledge/conflicts", headers=_headers("revision-other-owner"))
            assert isolated.status_code == 200
            assert isolated.json()["data"] == []
        finally:
            await client.aclose()


@pytest.mark.asyncio
async def test_workflow_artifact_fullstack_decision_memo_and_project_context(fullstack_gateway_config, migrated_knowledge_db) -> None:
    from app.gateway.app import create_app
    from deerflow.config.paths import get_paths

    app = create_app()
    async with app.router.lifespan_context(app):
        owner_id = "workflow-owner"
        paths = get_paths()
        paths.ensure_thread_dirs(owner_id, user_id=owner_id)
        upload_dir = paths.sandbox_uploads_dir(owner_id, user_id=owner_id)
        workflow_source = upload_dir / "workflow-evidence.txt"
        workflow_source.write_text(
            "Storage boundary is user scoped. Rollout risk is medium. Recommended option is staged launch.",
            encoding="utf-8",
        )

        client = _client(app)
        try:
            terminal = await _ingest_file(
                client,
                source_uri="/mnt/user-data/uploads/workflow-evidence.txt",
                media_type="text/plain",
                idempotency_key="workflow-evidence-v1",
                user_id=owner_id,
            )
            source_id = terminal["result_reference"]["source_id"]

            decision_input = {
                "workflow_type": "decision_memo",
                "input": {"decision": "Choose storage boundary", "source_ids": [source_id], "options": ["User scoped", "Shared global"]},
                "idempotency_key": "decision-memo-storage",
            }
            created = await client.post("/api/knowledge/workflows", json=decision_input, headers=_headers(owner_id))
            duplicate = await client.post("/api/knowledge/workflows", json=decision_input, headers=_headers(owner_id))
            assert created.status_code == 200
            assert duplicate.status_code == 200
            workflow_id = created.json()["workflow_run_id"]
            assert duplicate.json()["workflow_run_id"] == workflow_id
            assert len(created.json()["steps"]) == 3

            advanced = await client.post(f"/api/knowledge/workflows/{workflow_id}/advance", headers=_headers(owner_id))
            assert advanced.status_code == 200
            workflow_body = advanced.json()
            assert workflow_body["status"] == "completed", {"error": workflow_body.get("error"), "steps": workflow_body.get("steps")}
            assert workflow_body["artifact_ids"]
            assert {step["status"] for step in workflow_body["steps"]} == {"succeeded"}

            repeated = await client.post(f"/api/knowledge/workflows/{workflow_id}/advance", headers=_headers(owner_id))
            assert repeated.status_code == 200
            assert repeated.json()["artifact_ids"] == workflow_body["artifact_ids"]

            artifact_id = workflow_body["artifact_ids"][0]
            artifact = await client.get(f"/api/knowledge/artifacts/{artifact_id}", headers=_headers(owner_id))
            assert artifact.status_code == 200
            artifact_body = artifact.json()
            assert artifact_body["workflow_run_id"] == workflow_id
            assert artifact_body["artifact_type"] == "decision_memo"
            assert "Executive Summary" in artifact_body["markdown"]
            assert "Decision Context" in artifact_body["markdown"]
            assert "Options / Alternatives" in artifact_body["markdown"]
            assert "Evidence" in artifact_body["markdown"]
            assert "Risks" in artifact_body["markdown"]
            assert "Recommendation" in artifact_body["markdown"]
            assert "Open Questions" in artifact_body["markdown"]
            assert "Adoption / Next Steps" in artifact_body["markdown"]
            assert "References / Citations" in artifact_body["markdown"]
            assert artifact_body["evidence_links"]
            link = artifact_body["evidence_links"][0]
            assert link["source_id"] == source_id
            assert link["revision_id"]
            assert link["chunk_id"]
            assert link["claim_id"]
            chunk = await _chunk_by_id(app, link["chunk_id"])
            assert chunk.content[link["start_offset"] : link["end_offset"]] == link["quoted_text"]

            links = await client.get(f"/api/knowledge/artifacts/{artifact_id}/evidence-links", headers=_headers(owner_id))
            assert links.status_code == 200
            assert links.json()["data"]

            invalid = await client.post(f"/api/knowledge/workflows/{workflow_id}/pause", headers=_headers(owner_id))
            assert invalid.status_code == 409
            assert invalid.json()["detail"]["error"]["code"] == "invalid_workflow_transition"

            project = await client.post(
                "/api/knowledge/workflows",
                json={
                    "workflow_type": "project_context_pack",
                    "input": {"project": "Storage rollout", "source_ids": [source_id]},
                    "idempotency_key": "project-context-storage",
                },
                headers=_headers(owner_id),
            )
            assert project.status_code == 200
            project_id = project.json()["workflow_run_id"]
            paused = await client.post(f"/api/knowledge/workflows/{project_id}/pause", headers=_headers(owner_id))
            assert paused.status_code == 200
            assert paused.json()["status"] == "paused"
            resumed = await client.post(f"/api/knowledge/workflows/{project_id}/resume", headers=_headers(owner_id))
            assert resumed.status_code == 200
            assert resumed.json()["status"] == "completed"
            project_artifact = await client.get(f"/api/knowledge/artifacts/{resumed.json()['artifact_ids'][0]}", headers=_headers(owner_id))
            assert project_artifact.status_code == 200
            assert project_artifact.json()["artifact_type"] == "project_context_pack"
            assert project_artifact.json()["evidence_links"]

            retry_workflow = await client.post(
                "/api/knowledge/workflows",
                json={"workflow_type": "topic_dossier", "input": {"topic": "Retry path", "source_ids": [source_id]}},
                headers=_headers(owner_id),
            )
            retry_id = retry_workflow.json()["workflow_run_id"]
            await _mark_first_workflow_step_failed(app, retry_id)
            retried = await client.post(f"/api/knowledge/workflows/{retry_id}/retry", headers=_headers(owner_id))
            assert retried.status_code == 200
            assert retried.json()["status"] == "completed"
            assert retried.json()["steps"][0]["attempt"] == 1

            for workflow_type, input_payload in [
                ("reading_synthesis", {"reading_set": "Workflow reading", "source_ids": [source_id]}),
                ("meeting_preparation", {"meeting": "Workflow sync", "source_ids": [source_id]}),
                ("knowledge_update_review", {"source_id": source_id, "old_revision_id": "old-rev", "new_revision_id": "new-rev"}),
            ]:
                response = await client.post("/api/knowledge/workflows", json={"workflow_type": workflow_type, "input": input_payload}, headers=_headers(owner_id))
                assert response.status_code == 200
                assert response.json()["workflow_type"] == workflow_type

            action = await client.post(
                "/api/knowledge/workflows",
                json={"workflow_type": "knowledge_to_action", "input": {"objective": "Prepare action draft", "source_ids": [source_id]}},
                headers=_headers(owner_id),
            )
            assert action.status_code == 200
            action_advanced = await client.post(f"/api/knowledge/workflows/{action.json()['workflow_run_id']}/advance", headers=_headers(owner_id))
            assert action_advanced.status_code == 200
            assert action_advanced.json()["status"] == "requires_approval"
            assert action_advanced.json()["steps"][2]["output_payload"]["action_draft"]["executed"] is False

            workflows = await client.get("/api/knowledge/workflows?limit=100", headers=_headers(owner_id))
            assert workflows.status_code == 200
            workflow_types = {item["workflow_type"] for item in workflows.json()["data"]}
            assert {"decision_memo", "project_context_pack", "topic_dossier", "reading_synthesis", "meeting_preparation", "knowledge_update_review", "knowledge_to_action"} <= workflow_types

            isolated_workflow = await client.get(f"/api/knowledge/workflows/{workflow_id}", headers=_headers("workflow-other-owner"))
            isolated_artifact = await client.get(f"/api/knowledge/artifacts/{artifact_id}", headers=_headers("workflow-other-owner"))
            assert isolated_workflow.status_code == 404
            assert isolated_artifact.status_code == 404
        finally:
            await client.aclose()


@pytest.mark.asyncio
async def test_analysis_sync_result_citations_and_workspace_isolation(fullstack_gateway_config, migrated_knowledge_db) -> None:
    from app.gateway.app import create_app
    from deerflow.config.paths import get_paths

    app = create_app()
    async with app.router.lifespan_context(app):
        owner_id = "analysis-owner"
        paths = get_paths()
        paths.ensure_thread_dirs(owner_id, user_id=owner_id)
        upload_dir = paths.sandbox_uploads_dir(owner_id, user_id=owner_id)
        analysis_txt = upload_dir / "analysis-evidence.txt"
        analysis_md = upload_dir / "analysis-inference.md"
        analysis_txt.write_text(
            "Orion launch revenue was 42 dollars. Orion launch cost was 30 dollars.",
            encoding="utf-8",
        )
        analysis_md.write_text(
            "# Orion Notes\n\nThe direct margin evidence is split across revenue and cost notes.",
            encoding="utf-8",
        )

        client = _client(app)
        try:
            terminal = await _ingest_file(
                client,
                source_uri="/mnt/user-data/uploads/analysis-evidence.txt",
                media_type="text/plain",
                idempotency_key="analysis-evidence-once",
                user_id=owner_id,
            )
            await _ingest_file(
                client,
                source_uri="/mnt/user-data/uploads/analysis-inference.md",
                media_type="text/markdown",
                idempotency_key="analysis-inference-once",
                user_id=owner_id,
            )

            response = await client.post(
                "/api/knowledge/analyses",
                json={
                    "query": "What does the evidence say about Orion launch revenue, margin, and missing customer count?",
                    "context_budget": 4000,
                },
                headers=_headers(owner_id),
            )
            assert response.status_code == 200
            body = response.json()
            assert body["model_identity"] == "deterministic-analysis"
            assert body["query"].startswith("What does the evidence")
            assert body["supported_facts"], body
            assert body["inferred_conclusions"], body
            assert body["unsupported_or_insufficient_claims"] or body["unresolved_questions"], body

            fact = body["supported_facts"][0]
            assert "Orion launch revenue" in fact["statement"]
            citation = fact["citations"][0]
            assert citation["source_id"] == terminal["result_reference"]["source_id"]
            assert citation["revision_id"]
            assert citation["chunk_id"]
            assert citation["direct_evidence"] is True
            assert citation["is_context_expansion"] is False
            chunk = await _chunk_by_id(app, citation["chunk_id"])
            assert chunk.content[citation["start_offset"] : citation["end_offset"]] == citation["quoted_text"]

            inference = body["inferred_conclusions"][0]
            assert inference["is_inference"] is True
            assert inference["based_on_citations"]
            assert "inference" in inference["reasoning_summary"].lower()

            unresolved_text = " ".join([item["question"] + " " + item["needed_evidence"] for item in body["unresolved_questions"]] + [item["statement"] + " " + item["reason"] for item in body["unsupported_or_insufficient_claims"]])
            assert "customer" in unresolved_text.lower() or "missing" in unresolved_text.lower()

            for fact in body["supported_facts"]:
                assert any(citation["direct_evidence"] and not citation["is_context_expansion"] for citation in fact["citations"])

            isolated = await client.post(
                "/api/knowledge/analyses",
                json={"query": "What does the evidence say about Orion launch revenue?", "context_budget": 4000},
                headers=_headers("analysis-other-owner"),
            )
            assert isolated.status_code == 200
            isolated_body = isolated.json()
            assert isolated_body["supported_facts"] == []
            assert isolated_body["inferred_conclusions"] == []
            assert isolated_body["unsupported_or_insufficient_claims"] or isolated_body["unresolved_questions"]
        finally:
            await client.aclose()
