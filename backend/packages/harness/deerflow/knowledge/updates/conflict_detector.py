from __future__ import annotations

from typing import Protocol
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from deerflow.knowledge.enums import ClaimStatus, ConflictStatus
from deerflow.knowledge.models import Chunk, Claim, ClaimEvidenceLink, ConflictGroup, ConflictGroupClaim, DocumentRevision, EvidenceSpan
from deerflow.knowledge.updates.schemas import ConflictClassification, ConflictDecision, ConflictGroupResult


class ConflictClassifier(Protocol):
    async def classify(self, left: Claim, right: Claim) -> ConflictDecision: ...


class DeterministicConflictDetector:
    def __init__(self, classifier: ConflictClassifier | None = None) -> None:
        self._classifier = classifier

    async def detect_and_persist(self, session: AsyncSession, *, workspace_id: UUID, candidate_claim_ids: list[UUID]) -> list[ConflictGroupResult]:
        if not candidate_claim_ids:
            return []
        candidates = (
            (
                await session.execute(
                    select(Claim)
                    .where(
                        Claim.workspace_id == workspace_id,
                        Claim.id.in_(candidate_claim_ids),
                        Claim.status == ClaimStatus.ACTIVE,
                    )
                    .order_by(Claim.updated_at, Claim.id)
                )
            )
            .scalars()
            .all()
        )
        if not candidates:
            return []

        existing_claims = (
            (
                await session.execute(
                    select(Claim)
                    .where(
                        Claim.workspace_id == workspace_id,
                        Claim.status == ClaimStatus.ACTIVE,
                    )
                    .order_by(Claim.updated_at, Claim.id)
                )
            )
            .scalars()
            .all()
        )
        by_key: dict[tuple[str, str], list[Claim]] = {}
        for claim in existing_claims:
            key = _subject_predicate_key(claim)
            if key is None:
                continue
            by_key.setdefault(key, []).append(claim)

        results: list[ConflictGroupResult] = []
        seen_pairs: set[tuple[UUID, UUID]] = set()
        for new_claim in candidates:
            key = _subject_predicate_key(new_claim)
            if key is None:
                continue
            for other in by_key.get(key, []):
                if other.id == new_claim.id or other.id in candidate_claim_ids and str(other.id) > str(new_claim.id):
                    continue
                if not _can_conflict(new_claim, other):
                    continue
                pair = tuple(sorted((new_claim.id, other.id), key=str))
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                decision = await self._classify(session, new_claim, other)
                group = await _upsert_conflict_group(session, workspace_id, pair, key, decision)
                results.append(ConflictGroupResult(group.id, pair, decision.classification, decision.basis))
        return results

    async def _classify(self, session: AsyncSession, left: Claim, right: Claim) -> ConflictDecision:
        if self._classifier is not None:
            return await self._classifier.classify(left, right)
        if left.stance != right.stance and _same_object(left, right):
            return ConflictDecision(ConflictClassification.DIRECT_CONTRADICTION, "Same subject/predicate/object with opposing stance")
        left_source = await _claim_source_id(session, left)
        right_source = await _claim_source_id(session, right)
        if left_source is not None and left_source == right_source:
            return ConflictDecision(ConflictClassification.TEMPORAL_UPDATE, "Claims come from different revisions of the same source")
        if left_source is not None and right_source is not None and left_source != right_source:
            return ConflictDecision(ConflictClassification.SOURCE_DISAGREEMENT, "Claims come from different sources")
        return ConflictDecision(ConflictClassification.POSSIBLE_CONFLICT, "Same subject and predicate with different claim content")


def _subject_predicate_key(claim: Claim) -> tuple[str, str] | None:
    subject = _norm(claim.normalized_subject)
    predicate = _norm(claim.predicate)
    if not subject or not predicate:
        return None
    return subject, predicate


def _norm(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.casefold().split())
    return normalized or None


def _same_object(left: Claim, right: Claim) -> bool:
    return _norm(left.normalized_object) is not None and _norm(left.normalized_object) == _norm(right.normalized_object)


def _can_conflict(left: Claim, right: Claim) -> bool:
    if _norm(left.normalized_object) == _norm(right.normalized_object) and left.stance == right.stance:
        return False
    return left.claim_text.strip() != right.claim_text.strip() or left.stance != right.stance


async def _claim_source_id(session: AsyncSession, claim: Claim) -> UUID | None:
    row = (
        await session.execute(
            select(DocumentRevision.source_id)
            .join(Chunk, (Chunk.revision_id == DocumentRevision.id) & (Chunk.workspace_id == DocumentRevision.workspace_id))
            .join(EvidenceSpan, (EvidenceSpan.chunk_id == Chunk.id) & (EvidenceSpan.workspace_id == Chunk.workspace_id))
            .join(ClaimEvidenceLink, (ClaimEvidenceLink.evidence_span_id == EvidenceSpan.id) & (ClaimEvidenceLink.workspace_id == EvidenceSpan.workspace_id))
            .where(ClaimEvidenceLink.workspace_id == claim.workspace_id, ClaimEvidenceLink.claim_id == claim.id)
            .limit(1)
        )
    ).scalar_one_or_none()
    return row


async def _upsert_conflict_group(
    session: AsyncSession,
    workspace_id: UUID,
    pair: tuple[UUID, UUID],
    key: tuple[str, str],
    decision: ConflictDecision,
) -> ConflictGroup:
    existing = (
        await session.execute(
            select(ConflictGroup)
            .where(
                ConflictGroup.workspace_id == workspace_id,
                ConflictGroup.metadata_json["conflict_key"].as_string() == _conflict_key(pair),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.metadata_json = {
            **(existing.metadata_json or {}),
            "classification": decision.classification,
            "basis": decision.basis,
        }
        return existing

    group = ConflictGroup(
        workspace_id=workspace_id,
        topic=f"{key[0]}::{key[1]}",
        status=ConflictStatus.OPEN,
        summary=decision.basis,
        metadata_json={
            "conflict_key": _conflict_key(pair),
            "classification": decision.classification,
            "basis": decision.basis,
            "claim_ids": [str(item) for item in pair],
        },
    )
    session.add(group)
    await session.flush()
    for claim_id in pair:
        link_exists = (
            await session.execute(
                select(ConflictGroupClaim.id)
                .where(
                    and_(
                        ConflictGroupClaim.workspace_id == workspace_id,
                        ConflictGroupClaim.conflict_group_id == group.id,
                        ConflictGroupClaim.claim_id == claim_id,
                    )
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if link_exists is None:
            session.add(ConflictGroupClaim(workspace_id=workspace_id, conflict_group_id=group.id, claim_id=claim_id))
    await session.flush()
    return group


def _conflict_key(pair: tuple[UUID, UUID]) -> str:
    return ":".join(str(item) for item in pair)
