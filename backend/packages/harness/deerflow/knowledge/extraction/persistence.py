from __future__ import annotations

import hashlib
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from deerflow.knowledge.enums import ClaimStatus
from deerflow.knowledge.extraction.entity_resolver import EntityResolver
from deerflow.knowledge.extraction.schemas import ExtractedEvidenceSpan, StructuredExtractionOutput
from deerflow.knowledge.models import Chunk, Claim, ClaimEvidenceLink, EvidenceSpan, Relation


@dataclass(frozen=True)
class PersistedExtractionCounts:
    entity_count: int
    claim_count: int
    relation_count: int


class ExtractionPersistence:
    def __init__(self, *, entity_resolver: EntityResolver | None = None) -> None:
        self._entity_resolver = entity_resolver or EntityResolver()

    async def persist_chunk_output(
        self,
        session: AsyncSession,
        *,
        workspace_id: UUID,
        extraction_run_id: UUID,
        output: StructuredExtractionOutput,
        chunks_by_id: dict[UUID, Chunk],
    ) -> PersistedExtractionCounts:
        resolved_entities = await self._entity_resolver.resolve(session, workspace_id=workspace_id, extracted_entities=output.entities)
        evidence_cache: dict[tuple[UUID, int, int, str], EvidenceSpan] = {}
        entity_count = len({item.entity.id for item in resolved_entities.values()})
        claim_count = 0
        relation_count = 0

        for claim in output.claims:
            evidence_spans = [await self._get_or_create_evidence(session, workspace_id, span, chunks_by_id, evidence_cache) for span in claim.evidence_spans]
            if not evidence_spans:
                continue
            subject = resolved_entities[claim.subject_entity_local_id].entity
            object_entity = resolved_entities[claim.object_entity_local_id].entity if claim.object_entity_local_id else None
            extraction_key = _hash_key(
                "claim",
                str(subject.id),
                claim.predicate,
                str(object_entity.id) if object_entity else claim.object_text or "",
                claim.claim_text,
                ",".join(f"{span.chunk_id}:{span.start_offset}:{span.end_offset}" for span in claim.evidence_spans),
            )
            persisted_claim = await self._find_claim_by_key(session, workspace_id, extraction_key)
            if persisted_claim is None:
                persisted_claim = Claim(
                    workspace_id=workspace_id,
                    normalized_subject=subject.canonical_name,
                    predicate=claim.predicate,
                    normalized_object=object_entity.canonical_name if object_entity else claim.object_text,
                    claim_text=claim.claim_text,
                    stance=claim.stance,
                    confidence=claim.confidence,
                    valid_from=claim.valid_from,
                    valid_to=claim.valid_to,
                    status=ClaimStatus.ACTIVE,
                    metadata_json={
                        "extraction_key": extraction_key,
                        "extraction_run_id": str(extraction_run_id),
                        "subject_entity_id": str(subject.id),
                        "object_entity_id": str(object_entity.id) if object_entity else None,
                    },
                )
                session.add(persisted_claim)
                await session.flush()
            for evidence in evidence_spans:
                await self._ensure_claim_evidence_link(session, workspace_id, persisted_claim.id, evidence.id)
            claim_count += 1

        seen_relation_keys: set[str] = set()
        for relation in output.relations:
            source = resolved_entities[relation.source_entity_local_id].entity
            target = resolved_entities[relation.target_entity_local_id].entity
            for span in relation.evidence_spans:
                evidence = await self._get_or_create_evidence(session, workspace_id, span, chunks_by_id, evidence_cache)
                extraction_key = _hash_key("relation", str(source.id), relation.relation_type, str(target.id), str(evidence.id))
                if extraction_key in seen_relation_keys:
                    continue
                seen_relation_keys.add(extraction_key)
                existing = await self._find_relation(session, workspace_id, source.id, target.id, relation.relation_type, evidence.id)
                if existing is None:
                    session.add(
                        Relation(
                            workspace_id=workspace_id,
                            source_entity_id=source.id,
                            relation_type=relation.relation_type,
                            target_entity_id=target.id,
                            evidence_span_id=evidence.id,
                            confidence=relation.confidence,
                        )
                    )
                    await session.flush()
                relation_count += 1

        return PersistedExtractionCounts(entity_count=entity_count, claim_count=claim_count, relation_count=relation_count)

    async def _get_or_create_evidence(
        self,
        session: AsyncSession,
        workspace_id: UUID,
        span: ExtractedEvidenceSpan,
        chunks_by_id: dict[UUID, Chunk],
        evidence_cache: dict[tuple[UUID, int, int, str], EvidenceSpan],
    ) -> EvidenceSpan:
        key = (span.chunk_id, span.start_offset, span.end_offset, span.quoted_text)
        if key in evidence_cache:
            return evidence_cache[key]
        existing = (
            (
                await session.execute(
                    select(EvidenceSpan).where(
                        EvidenceSpan.workspace_id == workspace_id,
                        EvidenceSpan.chunk_id == span.chunk_id,
                        EvidenceSpan.start_offset == span.start_offset,
                        EvidenceSpan.end_offset == span.end_offset,
                        EvidenceSpan.quoted_text == span.quoted_text,
                    )
                )
            )
            .scalars()
            .first()
        )
        if existing is not None:
            evidence_cache[key] = existing
            return existing
        chunk = chunks_by_id[span.chunk_id]
        evidence = EvidenceSpan(
            workspace_id=workspace_id,
            chunk_id=span.chunk_id,
            start_offset=span.start_offset,
            end_offset=span.end_offset,
            quoted_text=span.quoted_text,
            page_number=chunk.page_number,
        )
        session.add(evidence)
        await session.flush()
        evidence_cache[key] = evidence
        return evidence

    async def _find_claim_by_key(self, session: AsyncSession, workspace_id: UUID, extraction_key: str) -> Claim | None:
        claims = (await session.execute(select(Claim).where(Claim.workspace_id == workspace_id))).scalars()
        return next((claim for claim in claims if (claim.metadata_json or {}).get("extraction_key") == extraction_key), None)

    async def _ensure_claim_evidence_link(self, session: AsyncSession, workspace_id: UUID, claim_id: UUID, evidence_span_id: UUID) -> None:
        existing = (
            (
                await session.execute(
                    select(ClaimEvidenceLink).where(
                        ClaimEvidenceLink.workspace_id == workspace_id,
                        ClaimEvidenceLink.claim_id == claim_id,
                        ClaimEvidenceLink.evidence_span_id == evidence_span_id,
                    )
                )
            )
            .scalars()
            .first()
        )
        if existing is None:
            session.add(ClaimEvidenceLink(workspace_id=workspace_id, claim_id=claim_id, evidence_span_id=evidence_span_id))
            await session.flush()

    async def _find_relation(
        self,
        session: AsyncSession,
        workspace_id: UUID,
        source_entity_id: UUID,
        target_entity_id: UUID,
        relation_type: str,
        evidence_span_id: UUID,
    ) -> Relation | None:
        return (
            (
                await session.execute(
                    select(Relation).where(
                        Relation.workspace_id == workspace_id,
                        Relation.source_entity_id == source_entity_id,
                        Relation.target_entity_id == target_entity_id,
                        Relation.relation_type == relation_type,
                        Relation.evidence_span_id == evidence_span_id,
                    )
                )
            )
            .scalars()
            .first()
        )


def _hash_key(*parts: str) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part.encode("utf-8"))
        digest.update(b"\x00")
    return digest.hexdigest()
