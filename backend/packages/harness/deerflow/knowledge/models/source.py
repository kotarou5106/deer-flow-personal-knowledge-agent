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

from deerflow.knowledge.enums import IndexStatus, JobStatus, ParseStatus, SourceStatus
from deerflow.knowledge.models.base import (
    JSONB,
    EmbeddingMixin,
    KnowledgeBase,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    WorkspaceMixin,
    utc_now,
)


class Source(UUIDPrimaryKeyMixin, WorkspaceMixin, TimestampMixin, KnowledgeBase):
    __tablename__ = "knowledge_sources"

    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    canonical_uri: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    author: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    latest_snapshot_id: Mapped[UUID | None] = mapped_column(postgresql.UUID(as_uuid=True), nullable=True)
    status: Mapped[SourceStatus] = mapped_column(Enum(SourceStatus, native_enum=False, create_constraint=True), nullable=False, default=SourceStatus.ACTIVE)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)

    __table_args__ = (
        UniqueConstraint("id", "workspace_id", name="uq_knowledge_sources_id_workspace"),
        UniqueConstraint("workspace_id", "source_type", "canonical_uri", name="uq_knowledge_sources_workspace_identity"),
        ForeignKeyConstraint(
            ["latest_snapshot_id", "workspace_id"],
            ["knowledge_source_snapshots.id", "knowledge_source_snapshots.workspace_id"],
            name="fk_knowledge_sources_latest_snapshot_workspace",
            use_alter=True,
            ondelete="SET NULL",
        ),
        Index("ix_knowledge_sources_workspace_status", "workspace_id", "status"),
    )


class SourceSnapshot(UUIDPrimaryKeyMixin, WorkspaceMixin, KnowledgeBase):
    __tablename__ = "knowledge_source_snapshots"

    source_id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    parser_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)

    __table_args__ = (
        UniqueConstraint("id", "workspace_id", name="uq_knowledge_snapshots_id_workspace"),
        UniqueConstraint("source_id", "content_hash", name="uq_knowledge_snapshots_source_hash"),
        ForeignKeyConstraint(["source_id", "workspace_id"], ["knowledge_sources.id", "knowledge_sources.workspace_id"], ondelete="RESTRICT"),
        Index("ix_knowledge_snapshots_workspace_source", "workspace_id", "source_id", "captured_at"),
    )


class DocumentRevision(UUIDPrimaryKeyMixin, WorkspaceMixin, KnowledgeBase):
    __tablename__ = "knowledge_document_revisions"

    source_id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    snapshot_id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    revision_number: Mapped[int] = mapped_column(nullable=False)
    previous_revision_id: Mapped[UUID | None] = mapped_column(postgresql.UUID(as_uuid=True), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    parse_status: Mapped[ParseStatus] = mapped_column(Enum(ParseStatus, native_enum=False, create_constraint=True), nullable=False, default=ParseStatus.PENDING)
    index_status: Mapped[IndexStatus] = mapped_column(Enum(IndexStatus, native_enum=False, create_constraint=True), nullable=False, default=IndexStatus.PENDING)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        UniqueConstraint("id", "workspace_id", name="uq_knowledge_revisions_id_workspace"),
        UniqueConstraint("source_id", "revision_number", name="uq_knowledge_revisions_source_number"),
        UniqueConstraint("source_id", "snapshot_id", "content_hash", name="uq_knowledge_revisions_source_snapshot_hash"),
        CheckConstraint("revision_number > 0", name="ck_knowledge_revisions_number_positive"),
        CheckConstraint("previous_revision_id IS NULL OR previous_revision_id <> id", name="ck_knowledge_revisions_previous_not_self"),
        ForeignKeyConstraint(["source_id", "workspace_id"], ["knowledge_sources.id", "knowledge_sources.workspace_id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["snapshot_id", "workspace_id"], ["knowledge_source_snapshots.id", "knowledge_source_snapshots.workspace_id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["previous_revision_id", "workspace_id"], ["knowledge_document_revisions.id", "knowledge_document_revisions.workspace_id"], ondelete="RESTRICT"),
        Index("ix_knowledge_revisions_workspace_source", "workspace_id", "source_id", "revision_number"),
    )


class Chunk(UUIDPrimaryKeyMixin, WorkspaceMixin, EmbeddingMixin, KnowledgeBase):
    __tablename__ = "knowledge_chunks"

    revision_id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    parent_chunk_id: Mapped[UUID | None] = mapped_column(postgresql.UUID(as_uuid=True), nullable=True)
    chunk_index: Mapped[int] = mapped_column(nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(nullable=False, default=0)
    page_number: Mapped[int | None] = mapped_column(nullable=True)
    section_path: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    start_offset: Mapped[int] = mapped_column(nullable=False)
    end_offset: Mapped[int] = mapped_column(nullable=False)
    content_tsv: Mapped[str | None] = mapped_column(postgresql.TSVECTOR, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        UniqueConstraint("id", "workspace_id", name="uq_knowledge_chunks_id_workspace"),
        UniqueConstraint("revision_id", "chunk_index", name="uq_knowledge_chunks_revision_index"),
        CheckConstraint("chunk_index >= 0", name="ck_knowledge_chunks_index_nonnegative"),
        CheckConstraint("token_count >= 0", name="ck_knowledge_chunks_token_count_nonnegative"),
        CheckConstraint("page_number IS NULL OR page_number > 0", name="ck_knowledge_chunks_page_positive"),
        CheckConstraint("start_offset <= end_offset", name="ck_knowledge_chunks_offsets_ordered"),
        CheckConstraint("length(btrim(content)) > 0", name="ck_knowledge_chunks_content_not_blank"),
        ForeignKeyConstraint(["revision_id", "workspace_id"], ["knowledge_document_revisions.id", "knowledge_document_revisions.workspace_id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["parent_chunk_id", "workspace_id"], ["knowledge_chunks.id", "knowledge_chunks.workspace_id"], ondelete="RESTRICT"),
        Index("ix_knowledge_chunks_workspace_revision", "workspace_id", "revision_id", "chunk_index"),
        Index("ix_knowledge_chunks_content_tsv", "content_tsv", postgresql_using="gin"),
    )


class IngestionJob(UUIDPrimaryKeyMixin, WorkspaceMixin, KnowledgeBase):
    __tablename__ = "knowledge_ingestion_jobs"

    source_id: Mapped[UUID | None] = mapped_column(postgresql.UUID(as_uuid=True), nullable=True)
    snapshot_id: Mapped[UUID | None] = mapped_column(postgresql.UUID(as_uuid=True), nullable=True)
    revision_id: Mapped[UUID | None] = mapped_column(postgresql.UUID(as_uuid=True), nullable=True)
    source_input: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus, native_enum=False, create_constraint=True), nullable=False, default=JobStatus.PENDING)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("id", "workspace_id", name="uq_knowledge_ingestion_jobs_id_workspace"),
        ForeignKeyConstraint(["source_id", "workspace_id"], ["knowledge_sources.id", "knowledge_sources.workspace_id"], ondelete="SET NULL"),
        ForeignKeyConstraint(["snapshot_id", "workspace_id"], ["knowledge_source_snapshots.id", "knowledge_source_snapshots.workspace_id"], ondelete="SET NULL"),
        ForeignKeyConstraint(["revision_id", "workspace_id"], ["knowledge_document_revisions.id", "knowledge_document_revisions.workspace_id"], ondelete="SET NULL"),
        Index("ix_knowledge_ingestion_jobs_workspace_status", "workspace_id", "status", "created_at"),
    )
