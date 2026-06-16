from __future__ import annotations

import math
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from deerflow.knowledge.models import Chunk, Claim, DocumentRevision, Entity, Source
from deerflow.knowledge.retrieval.indexing import EmbeddingModel
from deerflow.knowledge.retrieval.schemas import CandidateType, Provenance, QuerySpec, RetrievalCandidate, RetrievalChannel


class VectorRetriever:
    def __init__(self, embedding_model: EmbeddingModel | None = None, *, threshold: float = 0.0) -> None:
        self._embedding_model = embedding_model
        self._threshold = threshold

    async def retrieve(self, session: AsyncSession, *, workspace_id: UUID, query_spec: QuerySpec) -> list[RetrievalCandidate]:
        if self._embedding_model is None:
            return []
        query_vector = (await self._embedding_model.embed_texts([query_spec.query_text]))[0]
        if len(query_vector) != self._embedding_model.dimension:
            raise ValueError("Query embedding dimension mismatch")
        candidates = [
            *await self._retrieve_chunks(session, workspace_id, query_spec, query_vector),
            *await self._retrieve_entities(session, workspace_id, query_spec, query_vector),
            *await self._retrieve_claims(session, workspace_id, query_spec, query_vector),
        ]
        grouped: dict[RetrievalChannel, list[RetrievalCandidate]] = {}
        for candidate in candidates:
            grouped.setdefault(candidate.retrieval_channel, []).append(candidate)
        result: list[RetrievalCandidate] = []
        for channel_candidates in grouped.values():
            ordered = sorted(channel_candidates, key=lambda item: (-item.raw_score, str(item.candidate_id)))[: query_spec.top_k]
            for rank, candidate in enumerate(ordered, start=1):
                candidate.rank = rank
            result.extend(ordered)
        return result

    async def _retrieve_chunks(self, session: AsyncSession, workspace_id: UUID, query_spec: QuerySpec, query_vector: list[float]) -> list[RetrievalCandidate]:
        stmt = (
            select(Chunk, DocumentRevision, Source)
            .join(DocumentRevision, (Chunk.revision_id == DocumentRevision.id) & (Chunk.workspace_id == DocumentRevision.workspace_id))
            .join(Source, (DocumentRevision.source_id == Source.id) & (DocumentRevision.workspace_id == Source.workspace_id))
            .where(
                Chunk.workspace_id == workspace_id,
                Chunk.embedding.is_not(None),
                Chunk.embedding_model == self._embedding_model.model_identity,
                Chunk.embedding_dimension == self._embedding_model.dimension,
            )
        )
        if query_spec.source_ids:
            stmt = stmt.where(Source.id.in_(query_spec.source_ids))
        if query_spec.content_types:
            stmt = stmt.where(Source.source_type.in_(query_spec.content_types))
        if query_spec.date_range and query_spec.date_range.start:
            stmt = stmt.where(DocumentRevision.created_at >= query_spec.date_range.start)
        if query_spec.date_range and query_spec.date_range.end:
            stmt = stmt.where(DocumentRevision.created_at <= query_spec.date_range.end)
        rows = (await session.execute(stmt)).all()
        candidates: list[RetrievalCandidate] = []
        for rank, (chunk, revision, source) in enumerate(rows, start=1):
            score = cosine_similarity(query_vector, chunk.embedding or [])
            if score < self._threshold:
                continue
            candidates.append(
                RetrievalCandidate(
                    candidate_type=CandidateType.CHUNK,
                    candidate_id=chunk.id,
                    workspace_id=workspace_id,
                    source_id=source.id,
                    revision_id=revision.id,
                    chunk_id=chunk.id,
                    content=chunk.content,
                    retrieval_channel=RetrievalChannel.VECTOR_CHUNK,
                    raw_score=score,
                    rank=rank,
                    metadata={"distance": 1.0 - score, "parent_chunk_id": str(chunk.parent_chunk_id) if chunk.parent_chunk_id else None},
                    provenance=Provenance(source_id=source.id, snapshot_id=revision.snapshot_id, revision_id=revision.id, chunk_id=chunk.id, page_number=chunk.page_number),
                )
            )
        return candidates

    async def _retrieve_entities(self, session: AsyncSession, workspace_id: UUID, query_spec: QuerySpec, query_vector: list[float]) -> list[RetrievalCandidate]:
        rows = (
            await session.execute(
                select(Entity).where(
                    Entity.workspace_id == workspace_id,
                    Entity.embedding.is_not(None),
                    Entity.embedding_model == self._embedding_model.model_identity,
                    Entity.embedding_dimension == self._embedding_model.dimension,
                )
            )
        ).scalars()
        candidates = []
        for rank, entity in enumerate(rows, start=1):
            score = cosine_similarity(query_vector, entity.embedding or [])
            if score < self._threshold:
                continue
            candidates.append(
                RetrievalCandidate(
                    candidate_type=CandidateType.ENTITY,
                    candidate_id=entity.id,
                    workspace_id=workspace_id,
                    source_id=None,
                    revision_id=None,
                    chunk_id=None,
                    content=entity.canonical_name,
                    retrieval_channel=RetrievalChannel.VECTOR_ENTITY,
                    raw_score=score,
                    rank=rank,
                    metadata={"entity_type": entity.entity_type, "distance": 1.0 - score},
                    provenance=Provenance(),
                )
            )
        return candidates

    async def _retrieve_claims(self, session: AsyncSession, workspace_id: UUID, query_spec: QuerySpec, query_vector: list[float]) -> list[RetrievalCandidate]:
        rows = (
            await session.execute(
                select(Claim).where(
                    Claim.workspace_id == workspace_id,
                    Claim.embedding.is_not(None),
                    Claim.embedding_model == self._embedding_model.model_identity,
                    Claim.embedding_dimension == self._embedding_model.dimension,
                )
            )
        ).scalars()
        candidates = []
        for rank, claim in enumerate(rows, start=1):
            score = cosine_similarity(query_vector, claim.embedding or [])
            if score < self._threshold:
                continue
            candidates.append(
                RetrievalCandidate(
                    candidate_type=CandidateType.CLAIM,
                    candidate_id=claim.id,
                    workspace_id=workspace_id,
                    source_id=None,
                    revision_id=None,
                    chunk_id=None,
                    content=claim.claim_text,
                    retrieval_channel=RetrievalChannel.VECTOR_CLAIM,
                    raw_score=score,
                    rank=rank,
                    metadata={"distance": 1.0 - score},
                    provenance=Provenance(),
                )
            )
        return candidates


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)
