from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from deerflow.knowledge.enums import ArtifactStalenessStatus
from deerflow.knowledge.models import Artifact, ArtifactEvidenceLink, ClaimEvidenceLink, EvidenceSpan
from deerflow.knowledge.updates.schemas import StaleArtifactResult


async def mark_affected_artifacts_stale(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    removed_chunk_ids: list[UUID],
    modified_old_chunk_ids: list[UUID],
    superseded_claim_ids: list[UUID],
    conflict_group_ids: list[UUID],
    conflict_claim_ids: list[UUID] | None = None,
) -> list[StaleArtifactResult]:
    evidence_ids = await _evidence_ids_for_chunks(session, workspace_id, [*removed_chunk_ids, *modified_old_chunk_ids])
    artifact_reasons: dict[UUID, set[str]] = {}

    if evidence_ids:
        rows = (
            await session.execute(
                select(ArtifactEvidenceLink.artifact_id, ArtifactEvidenceLink.evidence_span_id).where(
                    ArtifactEvidenceLink.workspace_id == workspace_id,
                    ArtifactEvidenceLink.evidence_span_id.in_(evidence_ids),
                )
            )
        ).all()
        for artifact_id, evidence_id in rows:
            artifact_reasons.setdefault(artifact_id, set()).add(f"evidence_removed_or_modified:{evidence_id}")

    if superseded_claim_ids:
        rows = (
            await session.execute(
                select(ArtifactEvidenceLink.artifact_id, ArtifactEvidenceLink.claim_id).where(
                    ArtifactEvidenceLink.workspace_id == workspace_id,
                    ArtifactEvidenceLink.claim_id.in_(superseded_claim_ids),
                )
            )
        ).all()
        for artifact_id, claim_id in rows:
            artifact_reasons.setdefault(artifact_id, set()).add(f"claim_superseded:{claim_id}")

    conflict_claim_ids = conflict_claim_ids or []
    if conflict_group_ids and conflict_claim_ids:
        rows = (
            await session.execute(
                select(ArtifactEvidenceLink.artifact_id, ArtifactEvidenceLink.claim_id).where(
                    ArtifactEvidenceLink.workspace_id == workspace_id,
                    ArtifactEvidenceLink.claim_id.in_(conflict_claim_ids),
                )
            )
        ).all()
        for artifact_id, _ in rows:
            artifact_reasons.setdefault(artifact_id, set()).add("unresolved_conflict")

    results: list[StaleArtifactResult] = []
    if not artifact_reasons:
        return results

    artifacts = (
        (
            await session.execute(
                select(Artifact).where(
                    Artifact.workspace_id == workspace_id,
                    Artifact.id.in_(artifact_reasons),
                )
            )
        )
        .scalars()
        .all()
    )
    for artifact in artifacts:
        reasons = tuple(sorted(artifact_reasons[artifact.id]))
        artifact.staleness_status = ArtifactStalenessStatus.STALE
        artifact.metadata_json = {
            **(artifact.metadata_json or {}),
            "staleness_reasons": reasons,
            "requires_review": True,
            "conflict_group_ids": [str(item) for item in conflict_group_ids],
        }
        results.append(StaleArtifactResult(artifact.id, reasons))
    return sorted(results, key=lambda item: str(item.artifact_id))


async def _evidence_ids_for_chunks(session: AsyncSession, workspace_id: UUID, chunk_ids: list[UUID]) -> list[UUID]:
    if not chunk_ids:
        return []
    return list(
        (
            await session.execute(
                select(EvidenceSpan.id).where(
                    EvidenceSpan.workspace_id == workspace_id,
                    EvidenceSpan.chunk_id.in_(chunk_ids),
                )
            )
        ).scalars()
    )


async def claim_ids_for_chunks(session: AsyncSession, workspace_id: UUID, chunk_ids: list[UUID]) -> list[UUID]:
    evidence_ids = await _evidence_ids_for_chunks(session, workspace_id, chunk_ids)
    if not evidence_ids:
        return []
    return list(
        (
            await session.execute(
                select(ClaimEvidenceLink.claim_id).where(
                    ClaimEvidenceLink.workspace_id == workspace_id,
                    ClaimEvidenceLink.evidence_span_id.in_(evidence_ids),
                )
            )
        ).scalars()
    )
