from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKeyConstraint, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from deerflow.knowledge.enums import ArtifactStalenessStatus, ArtifactValidationStatus
from deerflow.knowledge.models.base import JSONB, KnowledgeBase, TimestampMixin, UUIDPrimaryKeyMixin, WorkspaceMixin, utc_now


class Artifact(UUIDPrimaryKeyMixin, WorkspaceMixin, TimestampMixin, KnowledgeBase):
    __tablename__ = "knowledge_artifacts"

    artifact_type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    validation_status: Mapped[ArtifactValidationStatus] = mapped_column(Enum(ArtifactValidationStatus, native_enum=False, create_constraint=True), nullable=False, default=ArtifactValidationStatus.PENDING)
    staleness_status: Mapped[ArtifactStalenessStatus] = mapped_column(Enum(ArtifactStalenessStatus, native_enum=False, create_constraint=True), nullable=False, default=ArtifactStalenessStatus.UNKNOWN)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)

    __table_args__ = (
        UniqueConstraint("id", "workspace_id", name="uq_knowledge_artifacts_id_workspace"),
        Index("ix_knowledge_artifacts_workspace_status", "workspace_id", "validation_status", "staleness_status"),
    )


class ArtifactEvidenceLink(UUIDPrimaryKeyMixin, WorkspaceMixin, KnowledgeBase):
    __tablename__ = "knowledge_artifact_evidence_links"

    artifact_id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    evidence_span_id: Mapped[UUID | None] = mapped_column(postgresql.UUID(as_uuid=True), nullable=True)
    claim_id: Mapped[UUID | None] = mapped_column(postgresql.UUID(as_uuid=True), nullable=True)
    revision_id: Mapped[UUID | None] = mapped_column(postgresql.UUID(as_uuid=True), nullable=True)
    usage_type: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        UniqueConstraint("artifact_id", "evidence_span_id", "claim_id", "revision_id", "usage_type", name="uq_knowledge_artifact_evidence_link"),
        ForeignKeyConstraint(["artifact_id", "workspace_id"], ["knowledge_artifacts.id", "knowledge_artifacts.workspace_id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["evidence_span_id", "workspace_id"], ["knowledge_evidence_spans.id", "knowledge_evidence_spans.workspace_id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["claim_id", "workspace_id"], ["knowledge_claims.id", "knowledge_claims.workspace_id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["revision_id", "workspace_id"], ["knowledge_document_revisions.id", "knowledge_document_revisions.workspace_id"], ondelete="RESTRICT"),
        Index("ix_knowledge_artifact_evidence_workspace_artifact", "workspace_id", "artifact_id"),
    )
