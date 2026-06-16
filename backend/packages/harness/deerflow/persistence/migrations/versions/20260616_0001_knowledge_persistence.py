"""Create Personal Knowledge Agent persistence tables.

Revision ID: 20260616_0001
Revises:
Create Date: 2026-06-16
"""

from __future__ import annotations

from alembic import op

from deerflow.knowledge.models import KnowledgeBase

revision = "20260616_0001"
down_revision = None
branch_labels = ("knowledge",)
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    KnowledgeBase.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    KnowledgeBase.metadata.drop_all(bind=bind)
    # Do not drop pgvector. The extension can be shared by other modules in the
    # same PostgreSQL database, so removing it here would be destructive.
