from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import desc

from deerflow.knowledge.models import Chunk, DocumentRevision, Source, SourceSnapshot
from deerflow.knowledge.repositories.base import WorkspaceRepository


class SourceRepository(WorkspaceRepository[Source]):
    model = Source

    async def get_by_canonical_identity(self, workspace_id: UUID, source_type: str, canonical_uri: str) -> Source | None:
        stmt = self._workspace_stmt(workspace_id).where(Source.source_type == source_type, Source.canonical_uri == canonical_uri)
        return await self._first(stmt)

    async def list(self, workspace_id: UUID, *, source_type: str | None = None, limit: int = 100, offset: int = 0) -> list[Source]:
        stmt = self._workspace_stmt(workspace_id)
        if source_type is not None:
            stmt = stmt.where(Source.source_type == source_type)
        return await self._all(stmt.order_by(Source.created_at.desc()).limit(limit).offset(offset))


class SnapshotRepository(WorkspaceRepository[SourceSnapshot]):
    model = SourceSnapshot

    async def get_by_source_and_hash(self, workspace_id: UUID, source_id: UUID, content_hash: str) -> SourceSnapshot | None:
        stmt = self._workspace_stmt(workspace_id).where(SourceSnapshot.source_id == source_id, SourceSnapshot.content_hash == content_hash)
        return await self._first(stmt)

    async def list_for_source(self, workspace_id: UUID, source_id: UUID) -> list[SourceSnapshot]:
        stmt = self._workspace_stmt(workspace_id).where(SourceSnapshot.source_id == source_id).order_by(SourceSnapshot.captured_at.desc())
        return await self._all(stmt)


class RevisionRepository(WorkspaceRepository[DocumentRevision]):
    model = DocumentRevision

    async def get_latest_for_source(self, workspace_id: UUID, source_id: UUID) -> DocumentRevision | None:
        stmt = self._workspace_stmt(workspace_id).where(DocumentRevision.source_id == source_id).order_by(desc(DocumentRevision.revision_number)).limit(1)
        return await self._first(stmt)

    async def list_for_source(self, workspace_id: UUID, source_id: UUID) -> list[DocumentRevision]:
        stmt = self._workspace_stmt(workspace_id).where(DocumentRevision.source_id == source_id).order_by(DocumentRevision.revision_number)
        return await self._all(stmt)


class ChunkRepository(WorkspaceRepository[Chunk]):
    model = Chunk

    async def list_for_revision(self, workspace_id: UUID, revision_id: UUID) -> list[Chunk]:
        stmt = self._workspace_stmt(workspace_id).where(Chunk.revision_id == revision_id).order_by(Chunk.chunk_index)
        return await self._all(stmt)

    async def bulk_add(self, chunks: Sequence[Chunk]) -> list[Chunk]:
        self.session.add_all(list(chunks))
        await self.session.flush()
        return list(chunks)
