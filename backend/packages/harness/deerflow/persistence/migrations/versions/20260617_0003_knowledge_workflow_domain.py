"""Add Knowledge workflow domain step tracking.

Revision ID: 20260617_0003
Revises: 20260617_0002
Create Date: 2026-06-17
"""

from __future__ import annotations

from alembic import op

revision = "20260617_0003"
down_revision = "20260617_0002"
branch_labels = None
depends_on = None

_WORKFLOW_STATUSES = "'DRAFT', 'READY', 'PENDING', 'RUNNING', 'PAUSED', 'COMPLETED', 'REQUIRES_APPROVAL', 'SUCCEEDED', 'FAILED', 'CANCELLED'"


def upgrade() -> None:
    op.execute("ALTER TABLE knowledge_workflow_runs ADD COLUMN IF NOT EXISTS idempotency_key VARCHAR(256)")
    op.execute("ALTER TABLE knowledge_workflow_runs ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb")
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_knowledge_workflow_runs_idempotency
            ON knowledge_workflow_runs (workspace_id, workflow_type, idempotency_key)
            WHERE idempotency_key IS NOT NULL
        """
    )
    op.execute("ALTER TABLE knowledge_workflow_runs DROP CONSTRAINT IF EXISTS workflowstatus")
    op.execute("ALTER TABLE knowledge_workflow_runs DROP CONSTRAINT IF EXISTS knowledge_workflow_runs_status_check")
    op.execute(
        f"""
        ALTER TABLE knowledge_workflow_runs
        ADD CONSTRAINT knowledge_workflow_runs_status_check
        CHECK (status IN ({_WORKFLOW_STATUSES}))
        """
    )
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS knowledge_workflow_step_runs (
            id UUID PRIMARY KEY,
            workspace_id UUID NOT NULL,
            workflow_run_id UUID NOT NULL,
            step_key VARCHAR(128) NOT NULL,
            sequence INTEGER NOT NULL,
            status VARCHAR(17) NOT NULL,
            input_payload JSONB NOT NULL,
            output_payload JSONB NOT NULL,
            attempt INTEGER NOT NULL,
            idempotency_key VARCHAR(256) NOT NULL,
            started_at TIMESTAMP WITH TIME ZONE,
            completed_at TIMESTAMP WITH TIME ZONE,
            error_type VARCHAR(128),
            error_message TEXT,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
            CONSTRAINT uq_knowledge_workflow_step_runs_id_workspace UNIQUE (id, workspace_id),
            CONSTRAINT uq_knowledge_workflow_steps_key UNIQUE (workflow_run_id, step_key),
            CONSTRAINT uq_knowledge_workflow_steps_sequence UNIQUE (workflow_run_id, sequence),
            CONSTRAINT uq_knowledge_workflow_steps_idempotency UNIQUE (workspace_id, idempotency_key),
            CONSTRAINT ck_knowledge_workflow_steps_sequence_nonnegative CHECK (sequence >= 0),
            CONSTRAINT ck_knowledge_workflow_steps_attempt_nonnegative CHECK (attempt >= 0),
            CONSTRAINT knowledge_workflow_step_runs_status_check CHECK (status IN ({_WORKFLOW_STATUSES})),
            CONSTRAINT fk_knowledge_workflow_steps_run_workspace
                FOREIGN KEY (workflow_run_id, workspace_id)
                REFERENCES knowledge_workflow_runs (id, workspace_id)
                ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_knowledge_workflow_steps_workspace_run
            ON knowledge_workflow_step_runs (workspace_id, workflow_run_id, sequence)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_knowledge_workflow_steps_workspace_status
            ON knowledge_workflow_step_runs (workspace_id, status, updated_at)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS knowledge_workflow_step_runs")
    op.execute("DROP INDEX IF EXISTS uq_knowledge_workflow_runs_idempotency")
    op.execute("ALTER TABLE knowledge_workflow_runs DROP CONSTRAINT IF EXISTS knowledge_workflow_runs_status_check")
    op.execute("UPDATE knowledge_workflow_runs SET status = 'SUCCEEDED' WHERE status = 'COMPLETED'")
    op.execute("UPDATE knowledge_workflow_runs SET status = 'PENDING' WHERE status IN ('DRAFT', 'READY', 'PAUSED', 'REQUIRES_APPROVAL')")
    op.execute(
        """
        ALTER TABLE knowledge_workflow_runs
        ADD CONSTRAINT knowledge_workflow_runs_status_check
        CHECK (status IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED'))
        """
    )
    op.execute("ALTER TABLE knowledge_workflow_runs DROP COLUMN IF EXISTS metadata")
    op.execute("ALTER TABLE knowledge_workflow_runs DROP COLUMN IF EXISTS idempotency_key")
