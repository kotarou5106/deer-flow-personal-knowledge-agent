"""Add Knowledge incremental update tracking.

Revision ID: 20260617_0002
Revises: 20260616_0001
Create Date: 2026-06-17
"""

from __future__ import annotations

from alembic import op

revision = "20260617_0002"
down_revision = "20260616_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS knowledge_update_runs (
            id UUID PRIMARY KEY,
            workspace_id UUID NOT NULL,
            old_revision_id UUID NOT NULL,
            new_revision_id UUID NOT NULL,
            updater_name VARCHAR(128) NOT NULL,
            updater_version VARCHAR(128) NOT NULL,
            status VARCHAR(9) NOT NULL,
            error TEXT,
            metadata JSONB NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,
            completed_at TIMESTAMP WITH TIME ZONE,
            CONSTRAINT uq_knowledge_update_runs_id_workspace UNIQUE (id, workspace_id),
            CONSTRAINT uq_knowledge_update_runs_revision_pair UNIQUE (
                workspace_id,
                old_revision_id,
                new_revision_id,
                updater_name,
                updater_version
            ),
            CONSTRAINT knowledge_update_runs_status_check CHECK (
                status IN ('pending', 'running', 'succeeded', 'failed', 'cancelled')
            ),
            CONSTRAINT fk_knowledge_update_runs_old_revision_workspace
                FOREIGN KEY (old_revision_id, workspace_id)
                REFERENCES knowledge_document_revisions (id, workspace_id)
                ON DELETE RESTRICT,
            CONSTRAINT fk_knowledge_update_runs_new_revision_workspace
                FOREIGN KEY (new_revision_id, workspace_id)
                REFERENCES knowledge_document_revisions (id, workspace_id)
                ON DELETE RESTRICT
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_knowledge_update_runs_workspace_status
            ON knowledge_update_runs (workspace_id, status, created_at)
        """
    )
    op.execute("ALTER TABLE knowledge_conflict_groups ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb")


def downgrade() -> None:
    op.execute("ALTER TABLE knowledge_conflict_groups DROP COLUMN IF EXISTS metadata")
    op.execute("DROP TABLE IF EXISTS knowledge_update_runs")
