from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, String
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON, TypeDecorator, UserDefinedType


def utc_now() -> datetime:
    return datetime.now(UTC)


class Vector(UserDefinedType):
    """Dimensionless pgvector column.

    Dimensions are stored per row so Knowledge can support multiple embedding
    models before Retrieval chooses metric-specific indexes.
    """

    cache_ok = True

    def get_col_spec(self, **_: object) -> str:
        return "vector"

    def bind_processor(self, dialect):
        def process(value: list[float] | tuple[float, ...] | str | None) -> str | None:
            if value is None:
                return None
            if isinstance(value, str):
                return value
            return "[" + ",".join(str(float(item)) for item in value) + "]"

        return process

    def result_processor(self, dialect, coltype):
        def process(value: list[float] | str | None) -> list[float] | None:
            if value is None:
                return None
            if isinstance(value, list):
                return value
            return [float(item) for item in value.strip("[]").split(",") if item]

        return process


class JSONB(TypeDecorator):
    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(postgresql.JSONB())
        return dialect.type_descriptor(JSON())


class KnowledgeBase(DeclarativeBase):
    pass


class UUIDPrimaryKeyMixin:
    id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), primary_key=True, default=uuid4)


class WorkspaceMixin:
    workspace_id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False, index=True)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class EmbeddingMixin:
    embedding: Mapped[list[float] | None] = mapped_column(Vector(), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(256), nullable=True)
    embedding_dimension: Mapped[int | None] = mapped_column(nullable=True)
    embedding_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    embedding_content_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
