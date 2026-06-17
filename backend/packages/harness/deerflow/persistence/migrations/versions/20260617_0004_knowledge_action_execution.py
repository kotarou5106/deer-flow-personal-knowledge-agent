"""Add Knowledge approval and action execution fields.

Revision ID: 20260617_0004
Revises: 20260617_0003
Create Date: 2026-06-17
"""

from __future__ import annotations

from alembic import op

revision = "20260617_0004"
down_revision = "20260617_0003"
branch_labels = None
depends_on = None

_ACTION_EXECUTION_STATUSES = "'PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED', 'RECONCILIATION_REQUIRED'"


def upgrade() -> None:
    op.execute("ALTER TABLE knowledge_approval_requests ADD COLUMN IF NOT EXISTS source_step_run_id UUID")
    op.execute("ALTER TABLE knowledge_approval_requests ADD COLUMN IF NOT EXISTS target VARCHAR(256) NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE knowledge_approval_requests ADD COLUMN IF NOT EXISTS action_payload JSONB NOT NULL DEFAULT '{}'::jsonb")
    op.execute("ALTER TABLE knowledge_approval_requests ADD COLUMN IF NOT EXISTS action_payload_hash VARCHAR(64) NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE knowledge_approval_requests ADD COLUMN IF NOT EXISTS requested_by VARCHAR(128)")
    op.execute("ALTER TABLE knowledge_approval_requests ADD COLUMN IF NOT EXISTS decision_reason TEXT")
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'fk_knowledge_approval_requests_step_workspace'
            ) THEN
                ALTER TABLE knowledge_approval_requests
                ADD CONSTRAINT fk_knowledge_approval_requests_step_workspace
                FOREIGN KEY (source_step_run_id, workspace_id)
                REFERENCES knowledge_workflow_step_runs (id, workspace_id)
                ON DELETE RESTRICT;
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_knowledge_approval_requests_workspace_hash
            ON knowledge_approval_requests (workspace_id, action_payload_hash)
        """
    )

    op.execute("ALTER TABLE knowledge_action_executions ADD COLUMN IF NOT EXISTS action_type VARCHAR(128) NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE knowledge_action_executions ADD COLUMN IF NOT EXISTS action_payload_hash VARCHAR(64) NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE knowledge_action_executions ADD COLUMN IF NOT EXISTS external_reference VARCHAR(512)")
    op.execute("ALTER TABLE knowledge_action_executions ADD COLUMN IF NOT EXISTS error_message TEXT")
    op.execute("ALTER TABLE knowledge_action_executions ADD COLUMN IF NOT EXISTS requires_reconciliation BOOLEAN NOT NULL DEFAULT false")
    op.execute("ALTER TABLE knowledge_action_executions ADD COLUMN IF NOT EXISTS started_at TIMESTAMP WITH TIME ZONE")
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'uq_knowledge_action_executions_approval'
            ) THEN
                ALTER TABLE knowledge_action_executions
                ADD CONSTRAINT uq_knowledge_action_executions_approval
                UNIQUE (approval_request_id);
            END IF;
        END $$;
        """
    )
    op.execute("ALTER TABLE knowledge_action_executions DROP CONSTRAINT IF EXISTS actionexecutionstatus")
    op.execute("ALTER TABLE knowledge_action_executions DROP CONSTRAINT IF EXISTS knowledge_action_executions_status_check")
    op.execute(
        f"""
        ALTER TABLE knowledge_action_executions
        ADD CONSTRAINT knowledge_action_executions_status_check
        CHECK (status IN ({_ACTION_EXECUTION_STATUSES}))
        """
    )


def downgrade() -> None:
    op.execute("UPDATE knowledge_action_executions SET status = 'FAILED' WHERE status = 'RECONCILIATION_REQUIRED'")
    op.execute("ALTER TABLE knowledge_action_executions DROP CONSTRAINT IF EXISTS knowledge_action_executions_status_check")
    op.execute(
        """
        ALTER TABLE knowledge_action_executions
        ADD CONSTRAINT knowledge_action_executions_status_check
        CHECK (status IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED'))
        """
    )
    op.execute("ALTER TABLE knowledge_action_executions DROP CONSTRAINT IF EXISTS uq_knowledge_action_executions_approval")
    op.execute("ALTER TABLE knowledge_action_executions DROP COLUMN IF EXISTS started_at")
    op.execute("ALTER TABLE knowledge_action_executions DROP COLUMN IF EXISTS requires_reconciliation")
    op.execute("ALTER TABLE knowledge_action_executions DROP COLUMN IF EXISTS error_message")
    op.execute("ALTER TABLE knowledge_action_executions DROP COLUMN IF EXISTS external_reference")
    op.execute("ALTER TABLE knowledge_action_executions DROP COLUMN IF EXISTS action_payload_hash")
    op.execute("ALTER TABLE knowledge_action_executions DROP COLUMN IF EXISTS action_type")

    op.execute("DROP INDEX IF EXISTS ix_knowledge_approval_requests_workspace_hash")
    op.execute("ALTER TABLE knowledge_approval_requests DROP CONSTRAINT IF EXISTS fk_knowledge_approval_requests_step_workspace")
    op.execute("ALTER TABLE knowledge_approval_requests DROP COLUMN IF EXISTS decision_reason")
    op.execute("ALTER TABLE knowledge_approval_requests DROP COLUMN IF EXISTS requested_by")
    op.execute("ALTER TABLE knowledge_approval_requests DROP COLUMN IF EXISTS action_payload_hash")
    op.execute("ALTER TABLE knowledge_approval_requests DROP COLUMN IF EXISTS action_payload")
    op.execute("ALTER TABLE knowledge_approval_requests DROP COLUMN IF EXISTS target")
    op.execute("ALTER TABLE knowledge_approval_requests DROP COLUMN IF EXISTS source_step_run_id")
