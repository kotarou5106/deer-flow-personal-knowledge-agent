from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy import func, select

from deerflow.knowledge.enums import JobStatus
from deerflow.knowledge.models import Chunk, Claim, Entity, IndexingRun
from deerflow.knowledge.unit_of_work import KnowledgeUnitOfWork, SessionFactory


class EmbeddingModelNotConfiguredError(RuntimeError):
    pass


class EmbeddingModel(Protocol):
    @property
    def model_identity(self) -> str: ...

    @property
    def dimension(self) -> int: ...

    async def embed_texts(self, texts: list[str]) -> list[list[float]]: ...


class IndexingService:
    def __init__(self, session_factory: SessionFactory, *, embedding_model: EmbeddingModel | None = None) -> None:
        self._session_factory = session_factory
        self._embedding_model = embedding_model

    async def index_revision(self, *, workspace_id: UUID, revision_id: UUID) -> UUID:
        run_id = uuid4()
        async with KnowledgeUnitOfWork(self._session_factory) as uow:
            assert uow.session is not None
            revision = await uow.revisions.get_by_id(workspace_id, revision_id)
            if revision is None:
                raise ValueError("Revision does not belong to workspace")
            uow.session.add(IndexingRun(id=run_id, workspace_id=workspace_id, revision_id=revision_id, index_type="hybrid", status=JobStatus.RUNNING))
            await uow.session.flush()
            try:
                chunks = await uow.chunks.list_for_revision(workspace_id, revision_id)
                for chunk in chunks:
                    chunk.content_tsv = func.to_tsvector("simple", chunk.content)
                if self._embedding_model is not None:
                    await self._embed_rows(chunks)
                    entities = (await uow.session.execute(select(Entity).where(Entity.workspace_id == workspace_id))).scalars().all()
                    claims = (await uow.session.execute(select(Claim).where(Claim.workspace_id == workspace_id))).scalars().all()
                    await self._embed_rows(list(entities))
                    await self._embed_rows(list(claims))
                run = await uow.session.get(IndexingRun, run_id)
                if run is not None:
                    run.status = JobStatus.SUCCEEDED
                    run.completed_at = datetime.now(UTC)
                await uow.commit()
            except Exception as exc:
                run = await uow.session.get(IndexingRun, run_id)
                if run is not None:
                    run.status = JobStatus.FAILED
                    run.error = str(exc)[:2000]
                    run.completed_at = datetime.now(UTC)
                await uow.commit()
                raise
        return run_id

    async def _embed_rows(self, rows: list[Chunk | Entity | Claim]) -> None:
        if self._embedding_model is None:
            raise EmbeddingModelNotConfiguredError("Embedding model is not configured")
        pending: list[tuple[Chunk | Entity | Claim, str, str]] = []
        for row in rows:
            text = _embedding_text(row)
            content_hash = sha256_text(text)
            if row.embedding is not None and row.embedding_model == self._embedding_model.model_identity and row.embedding_dimension == self._embedding_model.dimension and row.embedding_content_hash == content_hash:
                continue
            pending.append((row, text, content_hash))
        if not pending:
            return
        vectors = await self._embedding_model.embed_texts([item[1] for item in pending])
        if len(vectors) != len(pending):
            raise ValueError("Embedding model returned an unexpected vector count")
        now = datetime.now(UTC)
        for (row, _, content_hash), vector in zip(pending, vectors, strict=True):
            if len(vector) != self._embedding_model.dimension:
                raise ValueError("Embedding dimension mismatch")
            row.embedding = [float(value) for value in vector]
            row.embedding_model = self._embedding_model.model_identity
            row.embedding_dimension = self._embedding_model.dimension
            row.embedding_content_hash = content_hash
            row.embedding_updated_at = now


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _embedding_text(row: Chunk | Entity | Claim) -> str:
    if isinstance(row, Chunk):
        return row.content
    if isinstance(row, Entity):
        aliases = row.metadata_json.get("aliases", []) if row.metadata_json else []
        return "\n".join(filter(None, [row.canonical_name, row.entity_type or "", row.description or "", " ".join(aliases)]))
    return "\n".join(filter(None, [row.normalized_subject or "", row.predicate or "", row.normalized_object or "", row.claim_text]))
