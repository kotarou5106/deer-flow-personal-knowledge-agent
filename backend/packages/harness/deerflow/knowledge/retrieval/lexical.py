from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from deerflow.knowledge.models import Chunk, DocumentRevision, Source
from deerflow.knowledge.retrieval.schemas import CandidateType, Provenance, QuerySpec, RetrievalCandidate, RetrievalChannel


class LexicalRetriever:
    async def retrieve(self, session: AsyncSession, *, workspace_id: UUID, query_spec: QuerySpec) -> list[RetrievalCandidate]:
        terms = query_spec.keywords or [query_spec.query_text]
        stmt = (
            select(Chunk, DocumentRevision, Source)
            .join(DocumentRevision, (Chunk.revision_id == DocumentRevision.id) & (Chunk.workspace_id == DocumentRevision.workspace_id))
            .join(Source, (DocumentRevision.source_id == Source.id) & (DocumentRevision.workspace_id == Source.workspace_id))
            .where(Chunk.workspace_id == workspace_id)
        )
        if query_spec.source_ids:
            stmt = stmt.where(Source.id.in_(query_spec.source_ids))
        if query_spec.content_types:
            stmt = stmt.where(Source.source_type.in_(query_spec.content_types))
        if query_spec.date_range and query_spec.date_range.start:
            stmt = stmt.where(DocumentRevision.created_at >= query_spec.date_range.start)
        if query_spec.date_range and query_spec.date_range.end:
            stmt = stmt.where(DocumentRevision.created_at <= query_spec.date_range.end)
        conditions = []
        for term in terms:
            pattern = f"%{term}%"
            conditions.append(func.to_tsvector("simple", Chunk.content).op("@@")(func.plainto_tsquery("simple", term)))
            conditions.append(Chunk.content.ilike(pattern))
            conditions.append(Source.title.ilike(pattern))
        if conditions:
            stmt = stmt.where(or_(*conditions))
        rows = (await session.execute(stmt.order_by(Chunk.chunk_index).limit(query_spec.top_k * 4))).all()
        candidates: list[RetrievalCandidate] = []
        for rank, (chunk, revision, source) in enumerate(rows, start=1):
            score = _lexical_score(query_spec, chunk.content, source.title or "", chunk.section_path or [])
            candidates.append(
                RetrievalCandidate(
                    candidate_type=CandidateType.CHUNK,
                    candidate_id=chunk.id,
                    workspace_id=workspace_id,
                    source_id=source.id,
                    revision_id=revision.id,
                    chunk_id=chunk.id,
                    content=chunk.content,
                    retrieval_channel=RetrievalChannel.LEXICAL,
                    raw_score=score,
                    rank=rank,
                    metadata={
                        "parent_chunk_id": str(chunk.parent_chunk_id) if chunk.parent_chunk_id else None,
                        "section_path": list(chunk.section_path or []),
                        "source_title": source.title,
                    },
                    provenance=Provenance(
                        source_id=source.id,
                        snapshot_id=revision.snapshot_id,
                        revision_id=revision.id,
                        chunk_id=chunk.id,
                        page_number=chunk.page_number,
                        section_path=[str(part) for part in (chunk.section_path or [])],
                        start_offset=chunk.start_offset,
                        end_offset=chunk.end_offset,
                    ),
                )
            )
        return sorted(candidates, key=lambda item: (-item.raw_score, item.rank))[: query_spec.top_k]


def _lexical_score(query_spec: QuerySpec, content: str, title: str, section_path: list) -> float:
    haystacks = [content.casefold(), title.casefold(), " ".join(str(part) for part in section_path).casefold()]
    score = 0.0
    for term in query_spec.keywords or [query_spec.query_text]:
        key = term.casefold()
        if key in haystacks[0]:
            score += 2.0
        if key in haystacks[1]:
            score += 1.5
        if key in haystacks[2]:
            score += 1.0
    return score
