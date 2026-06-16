from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from deerflow.knowledge.models.base import JSONB, KnowledgeBase, UUIDPrimaryKeyMixin, WorkspaceMixin, utc_now


class AuditLog(UUIDPrimaryKeyMixin, WorkspaceMixin, KnowledgeBase):
    __tablename__ = "knowledge_audit_logs"

    actor_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    target_type: Mapped[str] = mapped_column(String(128), nullable=False)
    target_id: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        Index("ix_knowledge_audit_logs_workspace_created", "workspace_id", "created_at"),
        Index("ix_knowledge_audit_logs_workspace_target", "workspace_id", "target_type", "target_id"),
    )
