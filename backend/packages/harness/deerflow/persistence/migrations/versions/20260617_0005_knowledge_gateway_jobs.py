"""Add durable Knowledge gateway jobs.

Revision ID: 20260617_0005
Revises: 20260617_0004
Create Date: 2026-06-17
"""

from __future__ import annotations

from alembic import op

revision = "20260617_0005"
down_revision = "20260617_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS knowledge_jobs (
            id UUID PRIMARY KEY,
            workspace_id UUID NOT NULL,
            job_type VARCHAR(32) NOT NULL,
            status VARCHAR(32) NOT NULL,
            payload JSONB NOT NULL,
            payload_hash VARCHAR(64) NOT NULL,
            idempotency_key VARCHAR(256),
            attempt INTEGER NOT NULL,
            max_attempts INTEGER NOT NULL,
            progress JSONB NOT NULL,
            lease_owner VARCHAR(128),
            lease_expires_at TIMESTAMP WITH TIME ZONE,
            next_run_at TIMESTAMP WITH TIME ZONE NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
            started_at TIMESTAMP WITH TIME ZONE,
            completed_at TIMESTAMP WITH TIME ZONE,
            error_type VARCHAR(128),
            error_message TEXT,
            result_reference JSONB,
            CONSTRAINT uq_knowledge_jobs_id_workspace UNIQUE (id, workspace_id),
            CONSTRAINT uq_knowledge_jobs_idempotency_key UNIQUE (workspace_id, idempotency_key),
            CONSTRAINT ck_knowledge_jobs_attempt_nonnegative CHECK (attempt >= 0),
            CONSTRAINT ck_knowledge_jobs_max_attempts_positive CHECK (max_attempts > 0),
            CONSTRAINT ck_knowledge_jobs_payload_hash_length CHECK (length(payload_hash) = 64),
            CONSTRAINT knowledge_jobs_status_check CHECK (status IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCEL_REQUESTED', 'CANCELLED', 'RETRY_SCHEDULED')),
            CONSTRAINT knowledge_jobs_type_check CHECK (job_type IN ('INGEST', 'EXTRACT', 'INDEX', 'ANALYZE', 'INCREMENTAL_UPDATE', 'WORKFLOW_ADVANCE'))
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_knowledge_jobs_workspace_status_next ON knowledge_jobs (workspace_id, status, next_run_at, created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_knowledge_jobs_lease ON knowledge_jobs (lease_expires_at)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS knowledge_job_events (
            id UUID PRIMARY KEY,
            workspace_id UUID NOT NULL,
            job_id VARCHAR(36) NOT NULL,
            seq INTEGER NOT NULL,
            event_type VARCHAR(64) NOT NULL,
            payload JSONB NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,
            CONSTRAINT uq_knowledge_job_events_job_seq UNIQUE (workspace_id, job_id, seq),
            CONSTRAINT ck_knowledge_job_events_seq_positive CHECK (seq > 0)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_knowledge_job_events_workspace_job_seq ON knowledge_job_events (workspace_id, job_id, seq)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_knowledge_job_events_workspace_created ON knowledge_job_events (workspace_id, created_at, seq)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS knowledge_job_events")
    op.execute("DROP INDEX IF EXISTS ix_knowledge_jobs_workspace_status_next")
    op.execute("DROP INDEX IF EXISTS ix_knowledge_jobs_lease")
    op.execute("DROP TABLE IF EXISTS knowledge_jobs")
