"""Add Knowledge action execution idempotency table.

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

_ACTION_EXECUTION_STATUSES = "'PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED'"


def upgrade() -> None:
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS knowledge_action_executions (
            id UUID PRIMARY KEY,
            workspace_id UUID NOT NULL,
            approval_request_id UUID NOT NULL,
            connector_type VARCHAR(128) NOT NULL,
            idempotency_key VARCHAR(256) NOT NULL,
            request_payload JSONB NOT NULL,
            result_payload JSONB,
            status VARCHAR(9) NOT NULL,
            executed_at TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,
            CONSTRAINT uq_knowledge_action_executions_id_workspace UNIQUE (id, workspace_id),
            CONSTRAINT uq_knowledge_action_executions_idempotency UNIQUE (workspace_id, connector_type, idempotency_key),
            CONSTRAINT knowledge_action_executions_status_check CHECK (status IN ({_ACTION_EXECUTION_STATUSES})),
            CONSTRAINT fk_knowledge_action_executions_approval_workspace
                FOREIGN KEY (approval_request_id, workspace_id)
                REFERENCES knowledge_approval_requests (id, workspace_id)
                ON DELETE RESTRICT
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_knowledge_action_executions_workspace_status
            ON knowledge_action_executions (workspace_id, status, created_at)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS knowledge_action_executions")
