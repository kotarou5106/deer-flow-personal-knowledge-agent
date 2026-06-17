from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from deerflow.knowledge.enums import ClaimStance, ClaimStatus, ConflictStatus, JobStatus
from deerflow.knowledge.models.base import (
    JSONB,
    EmbeddingMixin,
    KnowledgeBase,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    WorkspaceMixin,
    utc_now,
)


class Entity(UUIDPrimaryKeyMixin, WorkspaceMixin, TimestampMixin, EmbeddingMixin, KnowledgeBase):
    __tablename__ = "knowledge_entities"

    canonical_name: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)

    __table_args__ = (
        UniqueConstraint("id", "workspace_id", name="uq_knowledge_entities_id_workspace"),
        CheckConstraint("length(btrim(canonical_name)) > 0", name="ck_knowledge_entities_name_not_blank"),
        Index("ix_knowledge_entities_workspace_name", "workspace_id", "canonical_name"),
    )


class EntityAlias(UUIDPrimaryKeyMixin, KnowledgeBase):
    __tablename__ = "knowledge_entity_aliases"

    entity_id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    workspace_id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    alias: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        UniqueConstraint("entity_id", "alias", name="uq_knowledge_entity_aliases_entity_alias"),
        CheckConstraint("length(btrim(alias)) > 0", name="ck_knowledge_entity_aliases_not_blank"),
        ForeignKeyConstraint(["entity_id", "workspace_id"], ["knowledge_entities.id", "knowledge_entities.workspace_id"], ondelete="CASCADE"),
        Index("ix_knowledge_entity_aliases_workspace_alias", "workspace_id", "alias"),
    )


class Claim(UUIDPrimaryKeyMixin, WorkspaceMixin, TimestampMixin, EmbeddingMixin, KnowledgeBase):
    __tablename__ = "knowledge_claims"

    normalized_subject: Mapped[str | None] = mapped_column(Text, nullable=True)
    predicate: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_object: Mapped[str | None] = mapped_column(Text, nullable=True)
    claim_text: Mapped[str] = mapped_column(Text, nullable=False)
    stance: Mapped[ClaimStance] = mapped_column(Enum(ClaimStance, native_enum=False, create_constraint=True), nullable=False, default=ClaimStance.NEUTRAL)
    confidence: Mapped[float | None] = mapped_column(nullable=True)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[ClaimStatus] = mapped_column(Enum(ClaimStatus, native_enum=False, create_constraint=True), nullable=False, default=ClaimStatus.STAGING)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)

    __table_args__ = (
        UniqueConstraint("id", "workspace_id", name="uq_knowledge_claims_id_workspace"),
        CheckConstraint("length(btrim(claim_text)) > 0", name="ck_knowledge_claims_text_not_blank"),
        CheckConstraint("confidence IS NULL OR (confidence >= 0 AND confidence <= 1)", name="ck_knowledge_claims_confidence_range"),
        CheckConstraint("valid_from IS NULL OR valid_to IS NULL OR valid_from <= valid_to", name="ck_knowledge_claims_validity_ordered"),
        Index("ix_knowledge_claims_workspace_status", "workspace_id", "status", "updated_at"),
    )


class EvidenceSpan(UUIDPrimaryKeyMixin, WorkspaceMixin, KnowledgeBase):
    __tablename__ = "knowledge_evidence_spans"

    chunk_id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    start_offset: Mapped[int] = mapped_column(nullable=False)
    end_offset: Mapped[int] = mapped_column(nullable=False)
    quoted_text: Mapped[str] = mapped_column(Text, nullable=False)
    page_number: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        UniqueConstraint("id", "workspace_id", name="uq_knowledge_evidence_spans_id_workspace"),
        CheckConstraint("start_offset <= end_offset", name="ck_knowledge_evidence_spans_offsets_ordered"),
        CheckConstraint("page_number IS NULL OR page_number > 0", name="ck_knowledge_evidence_spans_page_positive"),
        CheckConstraint("length(btrim(quoted_text)) > 0", name="ck_knowledge_evidence_spans_quote_not_blank"),
        ForeignKeyConstraint(["chunk_id", "workspace_id"], ["knowledge_chunks.id", "knowledge_chunks.workspace_id"], ondelete="RESTRICT"),
        Index("ix_knowledge_evidence_spans_workspace_chunk", "workspace_id", "chunk_id"),
    )


class ClaimEvidenceLink(UUIDPrimaryKeyMixin, WorkspaceMixin, KnowledgeBase):
    __tablename__ = "knowledge_claim_evidence_links"

    claim_id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    evidence_span_id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        UniqueConstraint("claim_id", "evidence_span_id", name="uq_knowledge_claim_evidence_link"),
        ForeignKeyConstraint(["claim_id", "workspace_id"], ["knowledge_claims.id", "knowledge_claims.workspace_id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["evidence_span_id", "workspace_id"], ["knowledge_evidence_spans.id", "knowledge_evidence_spans.workspace_id"], ondelete="RESTRICT"),
    )


class Relation(UUIDPrimaryKeyMixin, WorkspaceMixin, KnowledgeBase):
    __tablename__ = "knowledge_relations"

    source_entity_id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    relation_type: Mapped[str] = mapped_column(String(128), nullable=False)
    target_entity_id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    evidence_span_id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    confidence: Mapped[float | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        UniqueConstraint("id", "workspace_id", name="uq_knowledge_relations_id_workspace"),
        CheckConstraint("length(btrim(relation_type)) > 0", name="ck_knowledge_relations_type_not_blank"),
        CheckConstraint("confidence IS NULL OR (confidence >= 0 AND confidence <= 1)", name="ck_knowledge_relations_confidence_range"),
        CheckConstraint("source_entity_id <> target_entity_id", name="ck_knowledge_relations_distinct_entities"),
        ForeignKeyConstraint(["source_entity_id", "workspace_id"], ["knowledge_entities.id", "knowledge_entities.workspace_id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["target_entity_id", "workspace_id"], ["knowledge_entities.id", "knowledge_entities.workspace_id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["evidence_span_id", "workspace_id"], ["knowledge_evidence_spans.id", "knowledge_evidence_spans.workspace_id"], ondelete="RESTRICT"),
        Index("ix_knowledge_relations_workspace_source", "workspace_id", "source_entity_id"),
        Index("ix_knowledge_relations_workspace_target", "workspace_id", "target_entity_id"),
    )


class Collection(UUIDPrimaryKeyMixin, WorkspaceMixin, TimestampMixin, KnowledgeBase):
    __tablename__ = "knowledge_collections"

    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_id: Mapped[UUID | None] = mapped_column(postgresql.UUID(as_uuid=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("id", "workspace_id", name="uq_knowledge_collections_id_workspace"),
        UniqueConstraint("workspace_id", "name", name="uq_knowledge_collections_workspace_name"),
        CheckConstraint("length(btrim(name)) > 0", name="ck_knowledge_collections_name_not_blank"),
        ForeignKeyConstraint(["parent_id", "workspace_id"], ["knowledge_collections.id", "knowledge_collections.workspace_id"], ondelete="SET NULL"),
    )


class Topic(UUIDPrimaryKeyMixin, WorkspaceMixin, TimestampMixin, KnowledgeBase):
    __tablename__ = "knowledge_topics"

    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_id: Mapped[UUID | None] = mapped_column(postgresql.UUID(as_uuid=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("id", "workspace_id", name="uq_knowledge_topics_id_workspace"),
        UniqueConstraint("workspace_id", "name", name="uq_knowledge_topics_workspace_name"),
        CheckConstraint("length(btrim(name)) > 0", name="ck_knowledge_topics_name_not_blank"),
        ForeignKeyConstraint(["parent_id", "workspace_id"], ["knowledge_topics.id", "knowledge_topics.workspace_id"], ondelete="SET NULL"),
    )


class CollectionSource(UUIDPrimaryKeyMixin, WorkspaceMixin, KnowledgeBase):
    __tablename__ = "knowledge_collection_sources"
    collection_id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    source_id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    __table_args__ = (
        UniqueConstraint("collection_id", "source_id", name="uq_knowledge_collection_source"),
        ForeignKeyConstraint(["collection_id", "workspace_id"], ["knowledge_collections.id", "knowledge_collections.workspace_id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["source_id", "workspace_id"], ["knowledge_sources.id", "knowledge_sources.workspace_id"], ondelete="CASCADE"),
    )


class CollectionEntity(UUIDPrimaryKeyMixin, WorkspaceMixin, KnowledgeBase):
    __tablename__ = "knowledge_collection_entities"
    collection_id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    entity_id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    __table_args__ = (
        UniqueConstraint("collection_id", "entity_id", name="uq_knowledge_collection_entity"),
        ForeignKeyConstraint(["collection_id", "workspace_id"], ["knowledge_collections.id", "knowledge_collections.workspace_id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["entity_id", "workspace_id"], ["knowledge_entities.id", "knowledge_entities.workspace_id"], ondelete="CASCADE"),
    )


class CollectionClaim(UUIDPrimaryKeyMixin, WorkspaceMixin, KnowledgeBase):
    __tablename__ = "knowledge_collection_claims"
    collection_id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    claim_id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    __table_args__ = (
        UniqueConstraint("collection_id", "claim_id", name="uq_knowledge_collection_claim"),
        ForeignKeyConstraint(["collection_id", "workspace_id"], ["knowledge_collections.id", "knowledge_collections.workspace_id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["claim_id", "workspace_id"], ["knowledge_claims.id", "knowledge_claims.workspace_id"], ondelete="CASCADE"),
    )


class CollectionArtifact(UUIDPrimaryKeyMixin, WorkspaceMixin, KnowledgeBase):
    __tablename__ = "knowledge_collection_artifacts"
    collection_id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    artifact_id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    __table_args__ = (
        UniqueConstraint("collection_id", "artifact_id", name="uq_knowledge_collection_artifact"),
        ForeignKeyConstraint(["collection_id", "workspace_id"], ["knowledge_collections.id", "knowledge_collections.workspace_id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["artifact_id", "workspace_id"], ["knowledge_artifacts.id", "knowledge_artifacts.workspace_id"], ondelete="CASCADE"),
    )


class ExtractionRun(UUIDPrimaryKeyMixin, WorkspaceMixin, KnowledgeBase):
    __tablename__ = "knowledge_extraction_runs"
    revision_id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    model_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus, native_enum=False, create_constraint=True), nullable=False, default=JobStatus.PENDING)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        UniqueConstraint("id", "workspace_id", name="uq_knowledge_extraction_runs_id_workspace"),
        ForeignKeyConstraint(["revision_id", "workspace_id"], ["knowledge_document_revisions.id", "knowledge_document_revisions.workspace_id"], ondelete="RESTRICT"),
        Index("ix_knowledge_extraction_runs_workspace_revision", "workspace_id", "revision_id", "created_at"),
    )


class IndexingRun(UUIDPrimaryKeyMixin, WorkspaceMixin, KnowledgeBase):
    __tablename__ = "knowledge_indexing_runs"
    revision_id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    index_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus, native_enum=False, create_constraint=True), nullable=False, default=JobStatus.PENDING)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        UniqueConstraint("id", "workspace_id", name="uq_knowledge_indexing_runs_id_workspace"),
        ForeignKeyConstraint(["revision_id", "workspace_id"], ["knowledge_document_revisions.id", "knowledge_document_revisions.workspace_id"], ondelete="RESTRICT"),
        Index("ix_knowledge_indexing_runs_workspace_revision", "workspace_id", "revision_id", "created_at"),
    )


class KnowledgeUpdateRun(UUIDPrimaryKeyMixin, WorkspaceMixin, KnowledgeBase):
    __tablename__ = "knowledge_update_runs"
    old_revision_id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    new_revision_id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    updater_name: Mapped[str] = mapped_column(String(128), nullable=False)
    updater_version: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus, native_enum=False, create_constraint=True), nullable=False, default=JobStatus.PENDING)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        UniqueConstraint("id", "workspace_id", name="uq_knowledge_update_runs_id_workspace"),
        UniqueConstraint(
            "workspace_id",
            "old_revision_id",
            "new_revision_id",
            "updater_name",
            "updater_version",
            name="uq_knowledge_update_runs_revision_pair",
        ),
        ForeignKeyConstraint(["old_revision_id", "workspace_id"], ["knowledge_document_revisions.id", "knowledge_document_revisions.workspace_id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["new_revision_id", "workspace_id"], ["knowledge_document_revisions.id", "knowledge_document_revisions.workspace_id"], ondelete="RESTRICT"),
        Index("ix_knowledge_update_runs_workspace_status", "workspace_id", "status", "created_at"),
    )


class ConflictGroup(UUIDPrimaryKeyMixin, WorkspaceMixin, TimestampMixin, KnowledgeBase):
    __tablename__ = "knowledge_conflict_groups"
    topic: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ConflictStatus] = mapped_column(Enum(ConflictStatus, native_enum=False, create_constraint=True), nullable=False, default=ConflictStatus.OPEN)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    __table_args__ = (
        UniqueConstraint("id", "workspace_id", name="uq_knowledge_conflict_groups_id_workspace"),
        Index("ix_knowledge_conflict_groups_workspace_status", "workspace_id", "status"),
    )


class ConflictGroupClaim(UUIDPrimaryKeyMixin, WorkspaceMixin, KnowledgeBase):
    __tablename__ = "knowledge_conflict_group_claims"
    conflict_group_id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    claim_id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    __table_args__ = (
        UniqueConstraint("conflict_group_id", "claim_id", name="uq_knowledge_conflict_group_claim"),
        ForeignKeyConstraint(["conflict_group_id", "workspace_id"], ["knowledge_conflict_groups.id", "knowledge_conflict_groups.workspace_id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["claim_id", "workspace_id"], ["knowledge_claims.id", "knowledge_claims.workspace_id"], ondelete="RESTRICT"),
    )
