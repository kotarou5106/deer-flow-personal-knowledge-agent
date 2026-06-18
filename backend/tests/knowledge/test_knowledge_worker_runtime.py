from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.knowledge_runtime import (
    KnowledgeRuntime,
    KnowledgeWorkerConfigError,
    KnowledgeWorkerSettings,
    build_knowledge_runtime,
    embedded_worker_enabled,
    parse_knowledge_worker_settings,
)
from app.knowledge_worker import run_worker


def test_worker_settings_defaults() -> None:
    settings = parse_knowledge_worker_settings({})

    assert settings == KnowledgeWorkerSettings(
        worker_id=None,
        poll_interval_seconds=1.0,
        lease_ttl_seconds=30.0,
        shutdown_timeout_seconds=5.0,
    )


def test_worker_settings_parse_valid_values() -> None:
    settings = parse_knowledge_worker_settings(
        {
            "KNOWLEDGE_WORKER_ID": "worker-a",
            "KNOWLEDGE_WORKER_POLL_INTERVAL_SECONDS": "2.5",
            "KNOWLEDGE_WORKER_LEASE_TTL_SECONDS": "45",
            "KNOWLEDGE_WORKER_SHUTDOWN_TIMEOUT_SECONDS": "7",
        }
    )

    assert settings.worker_id == "worker-a"
    assert settings.poll_interval_seconds == 2.5
    assert settings.lease_ttl_seconds == 45.0
    assert settings.shutdown_timeout_seconds == 7.0


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("KNOWLEDGE_WORKER_POLL_INTERVAL_SECONDS", "not-a-number"),
        ("KNOWLEDGE_WORKER_LEASE_TTL_SECONDS", "not-a-number"),
        ("KNOWLEDGE_WORKER_SHUTDOWN_TIMEOUT_SECONDS", "not-a-number"),
        ("KNOWLEDGE_WORKER_POLL_INTERVAL_SECONDS", "0"),
        ("KNOWLEDGE_WORKER_LEASE_TTL_SECONDS", "-1"),
        ("KNOWLEDGE_WORKER_SHUTDOWN_TIMEOUT_SECONDS", "-0.25"),
    ],
)
def test_worker_settings_reject_invalid_values(variable: str, value: str) -> None:
    with pytest.raises(KnowledgeWorkerConfigError, match=variable):
        parse_knowledge_worker_settings({variable: value})


def test_embedded_worker_enabled_matches_existing_truthy_values() -> None:
    assert embedded_worker_enabled("1")
    assert embedded_worker_enabled("true")
    assert embedded_worker_enabled("YES")
    assert not embedded_worker_enabled("on")
    assert not embedded_worker_enabled("")


@pytest.mark.asyncio
async def test_build_runtime_initializes_provider_and_starts_worker(monkeypatch) -> None:
    events: list[object] = []

    class FakeProvider:
        def __init__(self) -> None:
            self.database = SimpleNamespace(session_factory=object())

        async def initialize(self) -> None:
            events.append("provider.initialize")

        async def dispose(self) -> None:
            events.append("provider.dispose")

    class FakeWorker:
        def __init__(self, **kwargs) -> None:
            events.append(("worker.init", kwargs))

        async def start(self) -> None:
            events.append("worker.start")

        async def shutdown(self) -> None:
            events.append("worker.shutdown")

    provider = FakeProvider()
    monkeypatch.setattr("app.knowledge_runtime.build_database_knowledge_service_provider", lambda _url: provider)
    monkeypatch.setattr("app.knowledge_runtime.provider_handlers", lambda value: {"provider": value})
    monkeypatch.setattr("app.knowledge_runtime.KnowledgeJobWorker", FakeWorker)
    monkeypatch.setattr("app.knowledge_runtime.set_knowledge_service_provider", lambda value: events.append(("set", value)))
    monkeypatch.setattr("app.knowledge_runtime.reset_knowledge_service_provider", lambda: events.append("reset"))

    runtime = await build_knowledge_runtime(
        "postgresql://example",
        worker_settings=KnowledgeWorkerSettings(worker_id="worker-a", poll_interval_seconds=2.0, lease_ttl_seconds=40.0, shutdown_timeout_seconds=6.0),
        start_worker=True,
    )

    assert runtime.provider is provider
    assert "provider.initialize" in events
    assert "worker.start" in events
    worker_init = next(item for item in events if isinstance(item, tuple) and item[0] == "worker.init")
    assert worker_init[1]["worker_id"] == "worker-a"
    assert worker_init[1]["poll_interval_seconds"] == 2.0
    assert worker_init[1]["lease_ttl_seconds"] == 40.0
    assert worker_init[1]["shutdown_timeout_seconds"] == 6.0

    await runtime.close()

    assert "worker.shutdown" in events
    assert "provider.dispose" in events
    assert "reset" in events


@pytest.mark.asyncio
async def test_build_runtime_disposes_provider_when_worker_start_fails(monkeypatch) -> None:
    events: list[str] = []

    class FakeProvider:
        def __init__(self) -> None:
            self.database = SimpleNamespace(session_factory=object())

        async def initialize(self) -> None:
            events.append("provider.initialize")

        async def dispose(self) -> None:
            events.append("provider.dispose")

    class FailingWorker:
        def __init__(self, **_kwargs) -> None:
            pass

        async def start(self) -> None:
            raise RuntimeError("start failed")

        async def shutdown(self) -> None:
            events.append("worker.shutdown")

    monkeypatch.setattr("app.knowledge_runtime.build_database_knowledge_service_provider", lambda _url: FakeProvider())
    monkeypatch.setattr("app.knowledge_runtime.provider_handlers", lambda _provider: {})
    monkeypatch.setattr("app.knowledge_runtime.KnowledgeJobWorker", FailingWorker)
    monkeypatch.setattr("app.knowledge_runtime.reset_knowledge_service_provider", lambda: events.append("reset"))

    with pytest.raises(RuntimeError, match="start failed"):
        await build_knowledge_runtime("postgresql://example", start_worker=True)

    assert events == ["provider.initialize", "worker.shutdown", "provider.dispose", "reset"]


@pytest.mark.asyncio
async def test_run_worker_requires_database_url() -> None:
    assert await run_worker(environ={}, register_signals=False) == 2


@pytest.mark.asyncio
async def test_run_worker_starts_waits_shuts_down_and_closes_runtime() -> None:
    events: list[str] = []
    stop_event = asyncio.Event()

    class FakeRuntime:
        async def close(self, *, timeout_seconds: float | None = None) -> None:
            events.append(f"close:{timeout_seconds}")

    async def runtime_factory(database_url: str, **kwargs) -> FakeRuntime:
        events.append(database_url)
        events.append(f"start_worker:{kwargs['start_worker']}")
        stop_event.set()
        return FakeRuntime()

    exit_code = await run_worker(
        environ={"KNOWLEDGE_DATABASE_URL": "postgresql://example", "KNOWLEDGE_WORKER_SHUTDOWN_TIMEOUT_SECONDS": "3"},
        shutdown_event=stop_event,
        register_signals=False,
        runtime_factory=runtime_factory,
    )

    assert exit_code == 0
    assert events == ["postgresql://example", "start_worker:True", "close:3.0"]


@pytest.mark.asyncio
async def test_run_worker_closes_runtime_after_wait_error() -> None:
    events: list[str] = []

    class FailingWaitEvent:
        async def wait(self) -> None:
            raise RuntimeError("wait failed")

    class FakeRuntime:
        async def close(self, *, timeout_seconds: float | None = None) -> None:
            events.append(f"close:{timeout_seconds}")

    async def runtime_factory(_database_url: str, **_kwargs) -> FakeRuntime:
        return FakeRuntime()

    exit_code = await run_worker(
        environ={"KNOWLEDGE_DATABASE_URL": "postgresql://example"},
        shutdown_event=FailingWaitEvent(),  # type: ignore[arg-type]
        register_signals=False,
        runtime_factory=runtime_factory,
    )

    assert exit_code == 1
    assert events == ["close:5.0"]


@pytest.mark.asyncio
async def test_runtime_close_disposes_provider_even_when_worker_shutdown_fails() -> None:
    events: list[str] = []

    class FailingWorker:
        async def shutdown(self) -> None:
            events.append("worker.shutdown")
            raise RuntimeError("shutdown failed")

    class FakeProvider:
        async def dispose(self) -> None:
            events.append("provider.dispose")

    runtime = KnowledgeRuntime(provider=FakeProvider(), job_service=object(), worker=FailingWorker(), install_global_provider=False)  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="shutdown failed"):
        await runtime.close()

    assert events == ["worker.shutdown", "provider.dispose"]
