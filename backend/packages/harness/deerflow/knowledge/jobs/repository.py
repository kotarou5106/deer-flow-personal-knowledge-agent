from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from deerflow.knowledge.jobs.models import KnowledgeJob, KnowledgeJobEvent, KnowledgeJobStatus, KnowledgeJobType


def utc_now() -> datetime:
    return datetime.now(UTC)


class KnowledgeJobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, job: KnowledgeJob) -> KnowledgeJob:
        self.session.add(job)
        await self.session.flush()
        return job

    async def get(self, workspace_id: UUID, job_id: UUID) -> KnowledgeJob | None:
        result = await self.session.execute(select(KnowledgeJob).where(KnowledgeJob.workspace_id == workspace_id, KnowledgeJob.id == job_id))
        return result.scalars().first()

    async def get_by_idempotency_key(self, workspace_id: UUID, idempotency_key: str) -> KnowledgeJob | None:
        stmt = select(KnowledgeJob).where(
            KnowledgeJob.workspace_id == workspace_id,
            KnowledgeJob.idempotency_key == idempotency_key,
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def list_for_workspace(self, workspace_id: UUID, *, limit: int, offset: int = 0) -> list[KnowledgeJob]:
        stmt = select(KnowledgeJob).where(KnowledgeJob.workspace_id == workspace_id).order_by(KnowledgeJob.created_at.desc(), KnowledgeJob.id.desc()).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def claim_next(
        self,
        *,
        worker_id: str,
        lease_ttl: timedelta,
        job_types: list[KnowledgeJobType] | None = None,
    ) -> KnowledgeJob | None:
        now = utc_now()
        statuses = [KnowledgeJobStatus.QUEUED, KnowledgeJobStatus.RETRY_SCHEDULED, KnowledgeJobStatus.RUNNING]
        stmt = (
            select(KnowledgeJob)
            .where(
                KnowledgeJob.status.in_(statuses),
                KnowledgeJob.next_run_at <= now,
                or_(KnowledgeJob.lease_expires_at.is_(None), KnowledgeJob.lease_expires_at <= now),
            )
            .order_by(KnowledgeJob.next_run_at.asc(), KnowledgeJob.created_at.asc())
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if job_types:
            stmt = stmt.where(KnowledgeJob.job_type.in_(job_types))
        result = await self.session.execute(stmt)
        job = result.scalars().first()
        if job is None:
            return None
        job.status = KnowledgeJobStatus.RUNNING
        job.lease_owner = worker_id
        job.lease_expires_at = now + lease_ttl
        job.started_at = job.started_at or now
        job.attempt += 1
        await self.session.flush()
        return job

    async def append_event(self, workspace_id: UUID, job_id: UUID | str, event_type: str, payload: dict) -> KnowledgeJobEvent:
        job_id_str = str(job_id)
        result = await self.session.execute(
            select(func.coalesce(func.max(KnowledgeJobEvent.seq), 0)).where(
                KnowledgeJobEvent.workspace_id == workspace_id,
                KnowledgeJobEvent.job_id == job_id_str,
            )
        )
        seq = int(result.scalar_one()) + 1
        event = KnowledgeJobEvent(workspace_id=workspace_id, job_id=job_id_str, seq=seq, event_type=event_type, payload=payload)
        self.session.add(event)
        await self.session.flush()
        return event

    async def list_events(self, workspace_id: UUID, job_id: UUID | str, *, after_seq: int | None = None, limit: int = 100) -> list[KnowledgeJobEvent]:
        stmt = select(KnowledgeJobEvent).where(KnowledgeJobEvent.workspace_id == workspace_id, KnowledgeJobEvent.job_id == str(job_id))
        if after_seq is not None:
            stmt = stmt.where(KnowledgeJobEvent.seq > after_seq)
        stmt = stmt.order_by(KnowledgeJobEvent.seq.asc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
