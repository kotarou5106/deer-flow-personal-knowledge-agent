from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from deerflow.knowledge.jobs.handlers import KnowledgeJobHandler
from deerflow.knowledge.jobs.models import KnowledgeJobStatus, KnowledgeJobType
from deerflow.knowledge.jobs.repository import KnowledgeJobRepository, utc_now
from deerflow.knowledge.runtime.context import TrustedKnowledgeContext
from deerflow.knowledge.unit_of_work import SessionFactory

logger = logging.getLogger(__name__)


class NonRetryableKnowledgeJobError(Exception):
    """Raised by handlers when retrying cannot make the job succeed."""


class KnowledgeJobWorker:
    def __init__(
        self,
        *,
        session_factory: SessionFactory,
        handlers: Mapping[KnowledgeJobType, KnowledgeJobHandler],
        poll_interval_seconds: float = 1.0,
        lease_ttl_seconds: float = 30.0,
        shutdown_timeout_seconds: float = 5.0,
        worker_id: str | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._handlers = dict(handlers)
        self._poll_interval_seconds = poll_interval_seconds
        self._lease_ttl = timedelta(seconds=lease_ttl_seconds)
        self._shutdown_timeout_seconds = shutdown_timeout_seconds
        self._worker_id = worker_id or f"knowledge-worker-{uuid4()}"
        self._stop = asyncio.Event()
        self._task: asyncio.Task | None = None

    @property
    def worker_id(self) -> str:
        return self._worker_id

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._stop.clear()
            self._task = asyncio.create_task(self._run(), name=self._worker_id)

    async def shutdown(self) -> None:
        self._stop.set()
        if self._task is None:
            return
        try:
            await asyncio.wait_for(self._task, timeout=self._shutdown_timeout_seconds)
        except TimeoutError:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)

    async def _run(self) -> None:
        while not self._stop.is_set():
            claimed = await self.run_once()
            if not claimed:
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=self._poll_interval_seconds)
                except TimeoutError:
                    pass

    async def run_once(self) -> bool:
        async with self._session_factory() as session:
            repo = KnowledgeJobRepository(session)
            job = await repo.claim_next(worker_id=self._worker_id, lease_ttl=self._lease_ttl, job_types=list(self._handlers))
            if job is None:
                await session.rollback()
                return False
            await repo.append_event(job.workspace_id, job.id, "job_started", {"attempt": job.attempt})
            await session.commit()

        handler = self._handlers.get(KnowledgeJobType(str(job.job_type)))
        if handler is None:
            await self._fail(job.id, job.workspace_id, "handler_not_configured", f"No handler configured for {job.job_type}")
            return True

        context = TrustedKnowledgeContext(
            user_id=str(job.payload.get("_trusted_user_id") or ""),
            workspace_id=job.workspace_id,
            thread_id=str(job.payload.get("_trusted_thread_id") or "knowledge-gateway"),
            actor_id=str(job.payload.get("_trusted_actor_id") or job.payload.get("_trusted_user_id") or ""),
            storage_root=Path(str(job.payload.get("_trusted_storage_root") or "/nonexistent")),
        )
        try:
            await self._progress(job.id, job.workspace_id, {"stage": "running", "percent": 10})
            result = await handler(context, job)
        except NonRetryableKnowledgeJobError as exc:
            logger.info("Knowledge job %s failed permanently: %s", job.id, type(exc).__name__)
            await self._fail(job.id, job.workspace_id, type(exc).__name__, str(exc), retryable=False)
            return True
        except Exception as exc:  # noqa: BLE001 - worker boundary stores sanitized failure
            logger.info("Knowledge job %s failed: %s", job.id, type(exc).__name__)
            await self._fail(job.id, job.workspace_id, type(exc).__name__, str(exc))
            return True
        await self._succeed(job.id, job.workspace_id, result)
        return True

    async def _progress(self, job_id, workspace_id, progress: dict) -> None:
        async with self._session_factory() as session:
            repo = KnowledgeJobRepository(session)
            job = await repo.get(workspace_id, job_id)
            if job is None or job.status == KnowledgeJobStatus.CANCEL_REQUESTED:
                return
            job.progress = progress
            await repo.append_event(workspace_id, job_id, "job_progress", progress)
            await session.commit()

    async def _succeed(self, job_id, workspace_id, result: dict) -> None:
        async with self._session_factory() as session:
            repo = KnowledgeJobRepository(session)
            job = await repo.get(workspace_id, job_id)
            if job is None:
                return
            now = utc_now()
            if job.status == KnowledgeJobStatus.CANCEL_REQUESTED:
                job.status = KnowledgeJobStatus.CANCELLED
                job.completed_at = now
                await repo.append_event(workspace_id, job_id, "job_cancelled", {})
            else:
                job.status = KnowledgeJobStatus.SUCCEEDED
                job.completed_at = now
                job.progress = {"stage": "succeeded", "percent": 100}
                job.result_reference = result
                await repo.append_event(workspace_id, job_id, "job_succeeded", {"result_reference": result})
            job.lease_owner = None
            job.lease_expires_at = None
            await session.commit()

    async def _fail(self, job_id, workspace_id, error_type: str, error_message: str, *, retryable: bool = True) -> None:
        async with self._session_factory() as session:
            repo = KnowledgeJobRepository(session)
            job = await repo.get(workspace_id, job_id)
            if job is None:
                return
            now = utc_now()
            job.lease_owner = None
            job.lease_expires_at = None
            job.error_type = error_type[:128]
            job.error_message = error_message[:2000]
            if retryable and job.attempt < job.max_attempts:
                delay = timedelta(seconds=min(60, 2 ** max(job.attempt - 1, 0)))
                job.status = KnowledgeJobStatus.RETRY_SCHEDULED
                job.next_run_at = now + delay
                await repo.append_event(workspace_id, job_id, "job_retry_scheduled", {"next_run_at": job.next_run_at.isoformat()})
            else:
                job.status = KnowledgeJobStatus.FAILED
                job.completed_at = now
                await repo.append_event(workspace_id, job_id, "job_failed", {"error_type": job.error_type, "error_message": job.error_message})
            await session.commit()
