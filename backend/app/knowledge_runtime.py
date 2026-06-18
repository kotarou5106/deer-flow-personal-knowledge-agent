from __future__ import annotations

import asyncio
import os
from collections.abc import Mapping
from dataclasses import dataclass
from types import TracebackType
from typing import Any

from deerflow.knowledge.jobs import KnowledgeJobService, KnowledgeJobWorker
from deerflow.knowledge.jobs.handlers import provider_handlers
from deerflow.knowledge.runtime.provider import (
    KnowledgeServiceProvider,
    build_database_knowledge_service_provider,
    reset_knowledge_service_provider,
    set_knowledge_service_provider,
)

TRUTHY_VALUES = {"1", "true", "yes"}


class KnowledgeWorkerConfigError(ValueError):
    """Raised when Knowledge worker environment config is invalid."""


@dataclass(frozen=True)
class KnowledgeWorkerSettings:
    worker_id: str | None = None
    poll_interval_seconds: float = 1.0
    lease_ttl_seconds: float = 30.0
    shutdown_timeout_seconds: float = 5.0


@dataclass
class KnowledgeRuntime:
    provider: KnowledgeServiceProvider
    job_service: KnowledgeJobService
    worker: KnowledgeJobWorker | None = None
    install_global_provider: bool = True

    async def close(self, *, timeout_seconds: float | None = None) -> None:
        first_error: BaseException | None = None
        if self.worker is not None:
            try:
                if timeout_seconds is None:
                    await self.worker.shutdown()
                else:
                    await asyncio.wait_for(self.worker.shutdown(), timeout=timeout_seconds)
            except BaseException as exc:
                first_error = exc
        try:
            if timeout_seconds is None:
                await self.provider.dispose()
            else:
                await asyncio.wait_for(self.provider.dispose(), timeout=timeout_seconds)
        except BaseException as exc:
            if first_error is None:
                first_error = exc
        finally:
            if self.install_global_provider:
                reset_knowledge_service_provider()
        if first_error is not None:
            raise first_error

    async def __aenter__(self) -> KnowledgeRuntime:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.close()


def embedded_worker_enabled(value: str | None) -> bool:
    return (value or "").strip().lower() in TRUTHY_VALUES


def parse_knowledge_worker_settings(environ: Mapping[str, str | None] | None = None) -> KnowledgeWorkerSettings:
    values = environ if environ is not None else os.environ
    return KnowledgeWorkerSettings(
        worker_id=_optional_str(values.get("KNOWLEDGE_WORKER_ID")),
        poll_interval_seconds=_positive_float(values.get("KNOWLEDGE_WORKER_POLL_INTERVAL_SECONDS"), "KNOWLEDGE_WORKER_POLL_INTERVAL_SECONDS", 1.0),
        lease_ttl_seconds=_positive_float(values.get("KNOWLEDGE_WORKER_LEASE_TTL_SECONDS"), "KNOWLEDGE_WORKER_LEASE_TTL_SECONDS", 30.0),
        shutdown_timeout_seconds=_positive_float(values.get("KNOWLEDGE_WORKER_SHUTDOWN_TIMEOUT_SECONDS"), "KNOWLEDGE_WORKER_SHUTDOWN_TIMEOUT_SECONDS", 5.0),
    )


async def build_knowledge_runtime(
    database_url: str,
    *,
    worker_settings: KnowledgeWorkerSettings | None = None,
    start_worker: bool = False,
    install_global_provider: bool = True,
) -> KnowledgeRuntime:
    settings = worker_settings or KnowledgeWorkerSettings()
    provider = build_database_knowledge_service_provider(database_url)
    worker: KnowledgeJobWorker | None = None
    try:
        await provider.initialize()
        if install_global_provider:
            set_knowledge_service_provider(provider)
        session_factory = _provider_session_factory(provider)
        job_service = KnowledgeJobService(session_factory)
        if start_worker:
            worker = KnowledgeJobWorker(
                session_factory=session_factory,
                handlers=provider_handlers(provider),
                poll_interval_seconds=settings.poll_interval_seconds,
                lease_ttl_seconds=settings.lease_ttl_seconds,
                shutdown_timeout_seconds=settings.shutdown_timeout_seconds,
                worker_id=settings.worker_id,
            )
            await worker.start()
        return KnowledgeRuntime(provider=provider, job_service=job_service, worker=worker, install_global_provider=install_global_provider)
    except BaseException:
        first_error: BaseException | None = None
        if worker is not None:
            try:
                await worker.shutdown()
            except BaseException as exc:
                first_error = exc
        try:
            await provider.dispose()
        except BaseException as exc:
            if first_error is None:
                first_error = exc
        if install_global_provider:
            reset_knowledge_service_provider()
        raise


def _optional_str(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _positive_float(value: str | None, variable_name: str, default: float) -> float:
    if value is None or value.strip() == "":
        return default
    try:
        parsed = float(value)
    except ValueError as exc:
        raise KnowledgeWorkerConfigError(f"{variable_name} must be a positive number") from exc
    if parsed <= 0:
        raise KnowledgeWorkerConfigError(f"{variable_name} must be greater than 0")
    return parsed


def _provider_session_factory(provider: KnowledgeServiceProvider) -> Any:
    database = getattr(provider, "database", None)
    session_factory = getattr(database, "session_factory", None)
    if session_factory is None:
        raise RuntimeError("Knowledge provider did not initialize a database session factory")
    return session_factory
