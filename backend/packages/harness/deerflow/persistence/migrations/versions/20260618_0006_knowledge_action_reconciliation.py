"""Allow Knowledge action reconciliation status.

Revision ID: 20260618_0006
Revises: 20260617_0005
Create Date: 2026-06-18
"""

from __future__ import annotations

from alembic import op

revision = "20260618_0006"
down_revision = "20260617_0005"
branch_labels = None
depends_on = None

_OLD_STATUSES = "'PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED'"
_NEW_STATUSES = "'PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED', 'RECONCILIATION_REQUIRED'"


def upgrade() -> None:
    op.execute("ALTER TABLE knowledge_action_executions DROP CONSTRAINT IF EXISTS knowledge_action_executions_status_check")
    op.execute("ALTER TABLE knowledge_action_executions ALTER COLUMN status TYPE VARCHAR(23)")
    op.execute(
        f"""
        ALTER TABLE knowledge_action_executions
        ADD CONSTRAINT knowledge_action_executions_status_check
        CHECK (status IN ({_NEW_STATUSES}))
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE knowledge_action_executions DROP CONSTRAINT IF EXISTS knowledge_action_executions_status_check")
    op.execute("UPDATE knowledge_action_executions SET status = 'FAILED' WHERE status = 'RECONCILIATION_REQUIRED'")
    op.execute("ALTER TABLE knowledge_action_executions ALTER COLUMN status TYPE VARCHAR(9)")
    op.execute(
        f"""
        ALTER TABLE knowledge_action_executions
        ADD CONSTRAINT knowledge_action_executions_status_check
        CHECK (status IN ({_OLD_STATUSES}))
        """
    )
