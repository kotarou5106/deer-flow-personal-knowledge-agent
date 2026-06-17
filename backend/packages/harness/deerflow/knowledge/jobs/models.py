from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from deerflow.knowledge.models.base import JSONB, KnowledgeBase, TimestampMixin, UUIDPrimaryKeyMixin, WorkspaceMixin, utc_now


class KnowledgeJobType(StrEnum):
    INGEST = "INGEST"
    EXTRACT = "EXTRACT"
    INDEX = "INDEX"
    ANALYZE = "ANALYZE"
    INCREMENTAL_UPDATE = "INCREMENTAL_UPDATE"
    WORKFLOW_ADVANCE = "WORKFLOW_ADVANCE"


class KnowledgeJobStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLED = "CANCELLED"
    RETRY_SCHEDULED = "RETRY_SCHEDULED"


TERMINAL_JOB_STATUSES = {
    KnowledgeJobStatus.SUCCEEDED,
    KnowledgeJobStatus.FAILED,
    KnowledgeJobStatus.CANCELLED,
}


class KnowledgeJob(UUIDPrimaryKeyMixin, WorkspaceMixin, TimestampMixin, KnowledgeBase):
    __tablename__ = "knowledge_jobs"

    job_type: Mapped[KnowledgeJobType] = mapped_column(String(32), nullable=False)
    status: Mapped[KnowledgeJobStatus] = mapped_column(String(32), nullable=False, default=KnowledgeJobStatus.QUEUED)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(256), nullable=True)
    attempt: Mapped[int] = mapped_column(nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(nullable=False, default=3)
    progress: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    lease_owner: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_reference: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        UniqueConstraint("id", "workspace_id", name="uq_knowledge_jobs_id_workspace"),
        UniqueConstraint("workspace_id", "idempotency_key", name="uq_knowledge_jobs_idempotency_key"),
        CheckConstraint("attempt >= 0", name="ck_knowledge_jobs_attempt_nonnegative"),
        CheckConstraint("max_attempts > 0", name="ck_knowledge_jobs_max_attempts_positive"),
        CheckConstraint("length(payload_hash) = 64", name="ck_knowledge_jobs_payload_hash_length"),
        CheckConstraint(
            "status IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCEL_REQUESTED', 'CANCELLED', 'RETRY_SCHEDULED')",
            name="knowledge_jobs_status_check",
        ),
        CheckConstraint(
            "job_type IN ('INGEST', 'EXTRACT', 'INDEX', 'ANALYZE', 'INCREMENTAL_UPDATE', 'WORKFLOW_ADVANCE')",
            name="knowledge_jobs_type_check",
        ),
        Index("ix_knowledge_jobs_workspace_status_next", "workspace_id", "status", "next_run_at", "created_at"),
        Index("ix_knowledge_jobs_lease", "lease_expires_at"),
    )


class KnowledgeJobEvent(UUIDPrimaryKeyMixin, WorkspaceMixin, KnowledgeBase):
    __tablename__ = "knowledge_job_events"

    job_id: Mapped[str] = mapped_column(String(36), nullable=False)
    seq: Mapped[int] = mapped_column(nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        UniqueConstraint("workspace_id", "job_id", "seq", name="uq_knowledge_job_events_job_seq"),
        CheckConstraint("seq > 0", name="ck_knowledge_job_events_seq_positive"),
        Index("ix_knowledge_job_events_workspace_job_seq", "workspace_id", "job_id", "seq"),
        Index("ix_knowledge_job_events_workspace_created", "workspace_id", "created_at", "seq"),
    )
