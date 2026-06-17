from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from typing import Any
from uuid import UUID

from deerflow.knowledge.jobs.models import TERMINAL_JOB_STATUSES, KnowledgeJob, KnowledgeJobEvent, KnowledgeJobStatus, KnowledgeJobType
from deerflow.knowledge.jobs.repository import KnowledgeJobRepository, utc_now
from deerflow.knowledge.unit_of_work import SessionFactory


def payload_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def job_to_dict(job: KnowledgeJob) -> dict[str, Any]:
    return {
        "job_id": str(job.id),
        "workspace_id": str(job.workspace_id),
        "job_type": str(job.job_type),
        "status": str(job.status),
        "payload_hash": job.payload_hash,
        "idempotency_key": job.idempotency_key,
        "attempt": job.attempt,
        "max_attempts": job.max_attempts,
        "progress": job.progress or {},
        "created_at": job.created_at.isoformat(),
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "error_type": job.error_type,
        "error_message": job.error_message,
        "result_reference": job.result_reference,
    }


def event_to_dict(event: KnowledgeJobEvent) -> dict[str, Any]:
    return {
        "event_id": str(event.id),
        "job_id": event.job_id,
        "seq": event.seq,
        "event_type": event.event_type,
        "payload": event.payload or {},
        "created_at": event.created_at.isoformat(),
    }


class KnowledgeJobService:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    async def enqueue(
        self,
        *,
        workspace_id: UUID,
        job_type: KnowledgeJobType,
        payload: dict[str, Any],
        idempotency_key: str | None = None,
        max_attempts: int = 3,
    ) -> KnowledgeJob:
        async with self._session_factory() as session:
            repo = KnowledgeJobRepository(session)
            if idempotency_key:
                existing = await repo.get_by_idempotency_key(workspace_id, idempotency_key)
                if existing is not None:
                    return existing
            job = await repo.add(
                KnowledgeJob(
                    workspace_id=workspace_id,
                    job_type=job_type,
                    status=KnowledgeJobStatus.QUEUED,
                    payload=payload,
                    payload_hash=payload_hash(payload),
                    idempotency_key=idempotency_key,
                    max_attempts=max_attempts,
                    progress={"stage": "queued", "percent": 0},
                )
            )
            await repo.append_event(workspace_id, job.id, "job_queued", {"job_type": job_type})
            await session.commit()
            return job

    async def get(self, workspace_id: UUID, job_id: UUID) -> KnowledgeJob | None:
        async with self._session_factory() as session:
            return await KnowledgeJobRepository(session).get(workspace_id, job_id)

    async def list(self, workspace_id: UUID, *, limit: int, offset: int = 0) -> list[KnowledgeJob]:
        async with self._session_factory() as session:
            return await KnowledgeJobRepository(session).list_for_workspace(workspace_id, limit=limit, offset=offset)

    async def retry(self, workspace_id: UUID, job_id: UUID, *, delay: timedelta = timedelta(seconds=1)) -> KnowledgeJob | None:
        async with self._session_factory() as session:
            repo = KnowledgeJobRepository(session)
            job = await repo.get(workspace_id, job_id)
            if job is None:
                return None
            if job.status == KnowledgeJobStatus.SUCCEEDED:
                return job
            now = utc_now()
            job.status = KnowledgeJobStatus.RETRY_SCHEDULED
            job.next_run_at = now + delay
            job.lease_owner = None
            job.lease_expires_at = None
            job.error_type = None
            job.error_message = None
            await repo.append_event(workspace_id, job.id, "job_retry_scheduled", {"next_run_at": job.next_run_at.isoformat()})
            await session.commit()
            return job

    async def cancel(self, workspace_id: UUID, job_id: UUID) -> KnowledgeJob | None:
        async with self._session_factory() as session:
            repo = KnowledgeJobRepository(session)
            job = await repo.get(workspace_id, job_id)
            if job is None:
                return None
            if job.status in TERMINAL_JOB_STATUSES:
                return job
            job.status = KnowledgeJobStatus.CANCEL_REQUESTED
            await repo.append_event(workspace_id, job.id, "job_cancel_requested", {})
            await session.commit()
            return job

    async def events(self, workspace_id: UUID, job_id: UUID, *, after_seq: int | None = None, limit: int = 100) -> list[KnowledgeJobEvent]:
        async with self._session_factory() as session:
            return await KnowledgeJobRepository(session).list_events(workspace_id, job_id, after_seq=after_seq, limit=limit)
