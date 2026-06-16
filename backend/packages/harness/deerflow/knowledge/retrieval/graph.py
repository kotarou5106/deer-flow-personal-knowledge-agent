from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from deerflow.knowledge.models import Chunk, Claim, ClaimEvidenceLink, DocumentRevision, Entity, EntityAlias, EvidenceSpan, Relation, Source
from deerflow.knowledge.retrieval.schemas import CandidateType, Provenance, QuerySpec, RetrievalCandidate, RetrievalChannel


class GraphRetriever:
    HARD_DEPTH_LIMIT = 2

    async def retrieve(self, session: AsyncSession, *, workspace_id: UUID, query_spec: QuerySpec) -> list[RetrievalCandidate]:
        depth = min(query_spec.graph_depth, self.HARD_DEPTH_LIMIT)
        if depth <= 0:
            return []
        start_entities = await self._find_start_entities(session, workspace_id, query_spec)
        if not start_entities:
            return []
        candidates: list[RetrievalCandidate] = []
        seen_entities = {entity.id for entity in start_entities}
        frontier = list(start_entities)
        for current_depth in range(depth):
            next_frontier: list[Entity] = []
            for entity in frontier:
                candidates.append(_entity_candidate(workspace_id, entity, len(candidates) + 1))
                relation_stmt = _apply_source_filters(
                    select(Relation, EvidenceSpan, Chunk, DocumentRevision, Source)
                    .join(
                        EvidenceSpan,
                        (Relation.evidence_span_id == EvidenceSpan.id) & (Relation.workspace_id == EvidenceSpan.workspace_id),
                    )
                    .join(Chunk, (EvidenceSpan.chunk_id == Chunk.id) & (EvidenceSpan.workspace_id == Chunk.workspace_id))
                    .join(
                        DocumentRevision,
                        (Chunk.revision_id == DocumentRevision.id) & (Chunk.workspace_id == DocumentRevision.workspace_id),
                    )
                    .join(Source, (DocumentRevision.source_id == Source.id) & (DocumentRevision.workspace_id == Source.workspace_id))
                    .where(
                        Relation.workspace_id == workspace_id,
                        (Relation.source_entity_id == entity.id) | (Relation.target_entity_id == entity.id),
                    ),
                    query_spec,
                )
                relations = await session.execute(relation_stmt)
                for relation, evidence, chunk, revision, source in relations.all():
                    candidates.append(_relation_candidate(workspace_id, relation, evidence, chunk, revision, source, len(candidates) + 1))
                    candidates.append(_evidence_candidate(workspace_id, evidence, chunk, revision, source, len(candidates) + 1))
                    other_id = relation.target_entity_id if relation.source_entity_id == entity.id else relation.source_entity_id
                    if current_depth + 1 < depth and other_id not in seen_entities:
                        other = await session.get(Entity, other_id)
                        if other is not None and other.workspace_id == workspace_id:
                            seen_entities.add(other.id)
                            next_frontier.append(other)
                claim_stmt = _apply_source_filters(
                    select(Claim, EvidenceSpan, Chunk, DocumentRevision, Source)
                    .join(
                        ClaimEvidenceLink,
                        (Claim.id == ClaimEvidenceLink.claim_id) & (Claim.workspace_id == ClaimEvidenceLink.workspace_id),
                    )
                    .join(
                        EvidenceSpan,
                        (ClaimEvidenceLink.evidence_span_id == EvidenceSpan.id) & (ClaimEvidenceLink.workspace_id == EvidenceSpan.workspace_id),
                    )
                    .join(Chunk, (EvidenceSpan.chunk_id == Chunk.id) & (EvidenceSpan.workspace_id == Chunk.workspace_id))
                    .join(
                        DocumentRevision,
                        (Chunk.revision_id == DocumentRevision.id) & (Chunk.workspace_id == DocumentRevision.workspace_id),
                    )
                    .join(Source, (DocumentRevision.source_id == Source.id) & (DocumentRevision.workspace_id == Source.workspace_id))
                    .where(Claim.workspace_id == workspace_id),
                    query_spec,
                )
                claims = await session.execute(claim_stmt)
                entity_id_text = str(entity.id)
                for claim, evidence, chunk, revision, source in claims.all():
                    metadata = claim.metadata_json or {}
                    if metadata.get("subject_entity_id") != entity_id_text and metadata.get("object_entity_id") != entity_id_text:
                        continue
                    candidates.append(_claim_candidate(workspace_id, claim, evidence, chunk, revision, source, len(candidates) + 1))
                    candidates.append(_evidence_candidate(workspace_id, evidence, chunk, revision, source, len(candidates) + 1))
            frontier = next_frontier
        return _dedupe(candidates)[: query_spec.top_k * 3]

    async def _find_start_entities(self, session: AsyncSession, workspace_id: UUID, query_spec: QuerySpec) -> list[Entity]:
        hints = query_spec.entity_hints or query_spec.keywords
        if not hints:
            return []
        entities = (await session.execute(select(Entity).where(Entity.workspace_id == workspace_id))).scalars().all()
        aliases = (await session.execute(select(EntityAlias, Entity).join(Entity, (EntityAlias.entity_id == Entity.id) & (EntityAlias.workspace_id == Entity.workspace_id)).where(EntityAlias.workspace_id == workspace_id))).all()
        results: list[Entity] = []
        seen: set[UUID] = set()
        for hint in hints:
            key = hint.casefold()
            for entity in entities:
                if key in entity.canonical_name.casefold() and entity.id not in seen:
                    seen.add(entity.id)
                    results.append(entity)
            for alias, entity in aliases:
                if key in alias.alias.casefold() and entity.id not in seen:
                    seen.add(entity.id)
                    results.append(entity)
        return results


def _entity_candidate(workspace_id: UUID, entity: Entity, rank: int) -> RetrievalCandidate:
    return RetrievalCandidate(CandidateType.ENTITY, entity.id, workspace_id, None, None, None, entity.canonical_name, RetrievalChannel.GRAPH, 1.0, rank, {"entity_type": entity.entity_type}, Provenance())


def _claim_candidate(workspace_id: UUID, claim: Claim, evidence: EvidenceSpan, chunk: Chunk, revision: DocumentRevision, source: Source, rank: int) -> RetrievalCandidate:
    return RetrievalCandidate(
        CandidateType.CLAIM,
        claim.id,
        workspace_id,
        source.id,
        revision.id,
        chunk.id,
        claim.claim_text,
        RetrievalChannel.GRAPH,
        1.0,
        rank,
        {"evidence_span_id": str(evidence.id)},
        Provenance(source_id=source.id, snapshot_id=revision.snapshot_id, revision_id=revision.id, chunk_id=chunk.id, evidence_span_id=evidence.id, page_number=evidence.page_number),
    )


def _relation_candidate(workspace_id: UUID, relation: Relation, evidence: EvidenceSpan, chunk: Chunk, revision: DocumentRevision, source: Source, rank: int) -> RetrievalCandidate:
    return RetrievalCandidate(
        CandidateType.RELATION,
        relation.id,
        workspace_id,
        source.id,
        revision.id,
        chunk.id,
        relation.relation_type,
        RetrievalChannel.GRAPH,
        1.0,
        rank,
        {"source_entity_id": str(relation.source_entity_id), "target_entity_id": str(relation.target_entity_id), "evidence_span_id": str(evidence.id)},
        Provenance(source_id=source.id, snapshot_id=revision.snapshot_id, revision_id=revision.id, chunk_id=chunk.id, evidence_span_id=evidence.id, page_number=evidence.page_number),
    )


def _evidence_candidate(workspace_id: UUID, evidence: EvidenceSpan, chunk: Chunk, revision: DocumentRevision, source: Source, rank: int) -> RetrievalCandidate:
    return RetrievalCandidate(
        CandidateType.EVIDENCE,
        evidence.id,
        workspace_id,
        source.id,
        revision.id,
        chunk.id,
        evidence.quoted_text,
        RetrievalChannel.GRAPH,
        1.0,
        rank,
        {"source_title": source.title},
        Provenance(
            source_id=source.id,
            snapshot_id=revision.snapshot_id,
            revision_id=revision.id,
            chunk_id=chunk.id,
            evidence_span_id=evidence.id,
            page_number=evidence.page_number,
            start_offset=evidence.start_offset,
            end_offset=evidence.end_offset,
        ),
    )


def _apply_source_filters(stmt, query_spec: QuerySpec):
    if query_spec.source_ids:
        stmt = stmt.where(Source.id.in_(query_spec.source_ids))
    if query_spec.content_types:
        stmt = stmt.where(Source.source_type.in_(query_spec.content_types))
    return stmt


def _dedupe(candidates: list[RetrievalCandidate]) -> list[RetrievalCandidate]:
    seen = set()
    result = []
    for candidate in candidates:
        if candidate.stable_key in seen:
            continue
        seen.add(candidate.stable_key)
        result.append(candidate)
    return result
