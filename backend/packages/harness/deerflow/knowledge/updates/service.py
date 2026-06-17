from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from deerflow.knowledge.enums import ClaimStatus, JobStatus
from deerflow.knowledge.models import (
    Claim,
    ClaimEvidenceLink,
    EvidenceSpan,
    KnowledgeUpdateRun,
)
from deerflow.knowledge.unit_of_work import KnowledgeUnitOfWork, SessionFactory
from deerflow.knowledge.updates.conflict_detector import ConflictClassifier, DeterministicConflictDetector
from deerflow.knowledge.updates.impact_analyzer import build_incremental_processing_plan
from deerflow.knowledge.updates.invalidation import claim_ids_for_chunks, mark_affected_artifacts_stale
from deerflow.knowledge.updates.revision_diff import diff_revisions
from deerflow.knowledge.updates.schemas import (
    UPDATER_NAME,
    UPDATER_VERSION,
    ClaimLifecycleStatus,
    ConflictGroupResult,
    KnowledgeUpdateReport,
    RevisionDiffSummary,
    StaleArtifactResult,
)


class ChunkProcessor(Protocol):
    async def process_chunk(self, *, workspace_id: UUID, revision_id: UUID, chunk_id: UUID) -> None: ...


class KnowledgeUpdateService:
    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        extraction_processor: ChunkProcessor | None = None,
        indexing_processor: ChunkProcessor | None = None,
        conflict_classifier: ConflictClassifier | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._extraction_processor = extraction_processor
        self._indexing_processor = indexing_processor
        self._conflict_detector = DeterministicConflictDetector(conflict_classifier)

    async def process_revision_update(self, *, workspace_id: UUID, old_revision_id: UUID, new_revision_id: UUID) -> KnowledgeUpdateReport:
        run = await self._start_or_resume_run(workspace_id, old_revision_id, new_revision_id)
        if run.status == JobStatus.SUCCEEDED and run.metadata_json.get("report"):
            return _report_from_metadata(run)

        diff, plan, source_id = await self._build_plan(workspace_id, old_revision_id, new_revision_id)
        errors: list[str] = []
        warnings: list[str] = []
        processed_chunk_ids = set(str(item) for item in (run.metadata_json or {}).get("processed_chunk_ids", []))

        for chunk_id in plan.reprocess_chunk_ids:
            if str(chunk_id) in processed_chunk_ids:
                continue
            try:
                await self._process_changed_chunk(workspace_id, new_revision_id, chunk_id)
                processed_chunk_ids.add(str(chunk_id))
                await self._record_processed_chunk(workspace_id, run.id, processed_chunk_ids)
            except Exception as exc:
                errors.append(f"chunk {chunk_id}: {exc}")

        superseded_claims: list[UUID] = []
        invalidated_claims: list[UUID] = []
        new_claims: list[UUID] = []
        conflicts: list[ConflictGroupResult] = []
        stale_artifacts: list[StaleArtifactResult] = []
        try:
            async with KnowledgeUnitOfWork(self._session_factory) as uow:
                assert uow.session is not None
                new_claims = await _claim_ids_for_chunks(uow.session, workspace_id, list(plan.reprocess_chunk_ids))
                modified_old_chunks = [pair.old_chunk_id for pair in diff.modified_pairs]
                removed_and_modified_old_chunks = [*diff.removed_chunk_ids, *modified_old_chunks]
                old_claims = await _claims_for_chunks(uow.session, workspace_id, removed_and_modified_old_chunks)
                new_active_claims = await _claims_for_chunks(uow.session, workspace_id, list(plan.reprocess_chunk_ids))
                superseded_claims, invalidated_claims = _apply_claim_lifecycle(old_claims, new_active_claims, removed_chunk_claim_ids=set(await claim_ids_for_chunks(uow.session, workspace_id, list(diff.removed_chunk_ids))))
                conflicts = await self._conflict_detector.detect_and_persist(uow.session, workspace_id=workspace_id, candidate_claim_ids=new_claims)
                conflict_claim_ids = sorted({claim_id for group in conflicts for claim_id in group.claim_ids}, key=str)
                await _mark_conflict_claims_pending(uow.session, workspace_id, conflict_claim_ids)
                stale_artifacts = await mark_affected_artifacts_stale(
                    uow.session,
                    workspace_id=workspace_id,
                    removed_chunk_ids=list(diff.removed_chunk_ids),
                    modified_old_chunk_ids=modified_old_chunks,
                    superseded_claim_ids=superseded_claims,
                    conflict_group_ids=[group.conflict_group_id for group in conflicts],
                    conflict_claim_ids=conflict_claim_ids,
                )
                await uow.commit()
        except Exception as exc:
            errors.append(f"finalization: {exc}")

        status = JobStatus.SUCCEEDED if not errors else JobStatus.FAILED
        report = KnowledgeUpdateReport(
            run_id=run.id,
            source_id=source_id,
            old_revision_id=old_revision_id,
            new_revision_id=new_revision_id,
            status=status,
            diff_summary=diff.summary,
            reprocessed_chunks=plan.reprocess_chunk_ids,
            reused_chunks=plan.reused_chunk_ids,
            superseded_claims=tuple(sorted(superseded_claims, key=str)),
            new_claims=tuple(sorted(new_claims, key=str)),
            conflict_groups=tuple(conflicts),
            stale_artifacts=tuple(stale_artifacts),
            warnings=tuple(warnings),
            errors=tuple(errors),
            metadata={"invalidated_claims": [str(item) for item in invalidated_claims]},
        )
        await self._complete_run(workspace_id, run.id, report, processed_chunk_ids)
        return report

    async def _start_or_resume_run(self, workspace_id: UUID, old_revision_id: UUID, new_revision_id: UUID) -> KnowledgeUpdateRun:
        async with KnowledgeUnitOfWork(self._session_factory) as uow:
            assert uow.session is not None
            existing = (
                await uow.session.execute(
                    select(KnowledgeUpdateRun).where(
                        KnowledgeUpdateRun.workspace_id == workspace_id,
                        KnowledgeUpdateRun.old_revision_id == old_revision_id,
                        KnowledgeUpdateRun.new_revision_id == new_revision_id,
                        KnowledgeUpdateRun.updater_name == UPDATER_NAME,
                        KnowledgeUpdateRun.updater_version == UPDATER_VERSION,
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                if existing.status != JobStatus.SUCCEEDED:
                    existing.status = JobStatus.RUNNING
                    existing.error = None
                await uow.commit()
                return existing
            run = KnowledgeUpdateRun(
                id=uuid4(),
                workspace_id=workspace_id,
                old_revision_id=old_revision_id,
                new_revision_id=new_revision_id,
                updater_name=UPDATER_NAME,
                updater_version=UPDATER_VERSION,
                status=JobStatus.RUNNING,
                metadata_json={},
            )
            uow.session.add(run)
            await uow.session.flush()
            await uow.commit()
            return run

    async def _build_plan(self, workspace_id: UUID, old_revision_id: UUID, new_revision_id: UUID):
        async with KnowledgeUnitOfWork(self._session_factory) as uow:
            old_revision = await uow.revisions.get_by_id(workspace_id, old_revision_id)
            new_revision = await uow.revisions.get_by_id(workspace_id, new_revision_id)
            if old_revision is None or new_revision is None:
                raise ValueError("Revision does not belong to workspace")
            old_chunks = await uow.chunks.list_for_revision(workspace_id, old_revision_id)
            new_chunks = await uow.chunks.list_for_revision(workspace_id, new_revision_id)
            diff = diff_revisions(old_revision, new_revision, old_chunks, new_chunks)
            return diff, build_incremental_processing_plan(diff), new_revision.source_id

    async def _process_changed_chunk(self, workspace_id: UUID, revision_id: UUID, chunk_id: UUID) -> None:
        if self._extraction_processor is not None:
            await self._extraction_processor.process_chunk(workspace_id=workspace_id, revision_id=revision_id, chunk_id=chunk_id)
        if self._indexing_processor is not None:
            await self._indexing_processor.process_chunk(workspace_id=workspace_id, revision_id=revision_id, chunk_id=chunk_id)

    async def _record_processed_chunk(self, workspace_id: UUID, run_id: UUID, processed_chunk_ids: set[str]) -> None:
        async with KnowledgeUnitOfWork(self._session_factory) as uow:
            assert uow.session is not None
            run = await uow.session.get(KnowledgeUpdateRun, run_id)
            if run is not None and run.workspace_id == workspace_id:
                run.metadata_json = {
                    **(run.metadata_json or {}),
                    "processed_chunk_ids": sorted(processed_chunk_ids),
                }
            await uow.commit()

    async def _complete_run(self, workspace_id: UUID, run_id: UUID, report: KnowledgeUpdateReport, processed_chunk_ids: set[str]) -> None:
        async with KnowledgeUnitOfWork(self._session_factory) as uow:
            assert uow.session is not None
            run = await uow.session.get(KnowledgeUpdateRun, run_id)
            if run is not None and run.workspace_id == workspace_id:
                run.status = report.status
                run.error = "\n".join(report.errors)[:2000] if report.errors else None
                run.completed_at = datetime.now(UTC)
                run.metadata_json = {
                    **(run.metadata_json or {}),
                    "processed_chunk_ids": sorted(processed_chunk_ids),
                    "report": _report_to_metadata(report),
                }
            await uow.commit()


async def _claim_ids_for_chunks(session: AsyncSession, workspace_id: UUID, chunk_ids: list[UUID]) -> list[UUID]:
    return [claim.id for claim in await _claims_for_chunks(session, workspace_id, chunk_ids)]


async def _claims_for_chunks(session: AsyncSession, workspace_id: UUID, chunk_ids: list[UUID]) -> list[Claim]:
    if not chunk_ids:
        return []
    return list(
        (
            await session.execute(
                select(Claim)
                .join(ClaimEvidenceLink, (ClaimEvidenceLink.claim_id == Claim.id) & (ClaimEvidenceLink.workspace_id == Claim.workspace_id))
                .join(EvidenceSpan, (EvidenceSpan.id == ClaimEvidenceLink.evidence_span_id) & (EvidenceSpan.workspace_id == ClaimEvidenceLink.workspace_id))
                .where(
                    Claim.workspace_id == workspace_id,
                    EvidenceSpan.chunk_id.in_(chunk_ids),
                )
                .order_by(Claim.updated_at, Claim.id)
            )
        ).scalars()
    )


def _apply_claim_lifecycle(old_claims: list[Claim], new_claims: list[Claim], *, removed_chunk_claim_ids: set[UUID]) -> tuple[list[UUID], list[UUID]]:
    active_new_by_triple = {_claim_triple(claim): claim for claim in new_claims if _claim_triple(claim) is not None}
    superseded: list[UUID] = []
    invalidated: list[UUID] = []
    for old_claim in old_claims:
        triple = _claim_triple(old_claim)
        if triple is not None and triple in active_new_by_triple:
            old_claim.status = ClaimStatus.SUPERSEDED
            old_claim.metadata_json = {
                **(old_claim.metadata_json or {}),
                "lifecycle_status": ClaimLifecycleStatus.SUPERSEDED,
                "superseded_by_claim_id": str(active_new_by_triple[triple].id),
            }
            superseded.append(old_claim.id)
        elif old_claim.id in removed_chunk_claim_ids:
            old_claim.status = ClaimStatus.INVALIDATED
            old_claim.metadata_json = {
                **(old_claim.metadata_json or {}),
                "lifecycle_status": ClaimLifecycleStatus.INVALID_EVIDENCE_REMOVED,
            }
            invalidated.append(old_claim.id)
    for new_claim in new_claims:
        new_claim.metadata_json = {
            **(new_claim.metadata_json or {}),
            "lifecycle_status": ClaimLifecycleStatus.CURRENT_ACTIVE,
        }
    return superseded, invalidated


async def _mark_conflict_claims_pending(session: AsyncSession, workspace_id: UUID, claim_ids: list[UUID]) -> None:
    if not claim_ids:
        return
    claims = (
        await session.execute(
            select(Claim).where(
                Claim.workspace_id == workspace_id,
                Claim.id.in_(claim_ids),
            )
        )
    ).scalars()
    for claim in claims:
        claim.metadata_json = {
            **(claim.metadata_json or {}),
            "lifecycle_status": ClaimLifecycleStatus.PENDING_CONFLICT_REVIEW,
        }


def _claim_triple(claim: Claim) -> tuple[str, str, str] | None:
    if not claim.normalized_subject or not claim.predicate or not claim.normalized_object:
        return None
    return (
        " ".join(claim.normalized_subject.casefold().split()),
        " ".join(claim.predicate.casefold().split()),
        " ".join(claim.normalized_object.casefold().split()),
    )


def _report_to_metadata(report: KnowledgeUpdateReport) -> dict:
    return {
        "run_id": str(report.run_id),
        "source_id": str(report.source_id),
        "old_revision_id": str(report.old_revision_id),
        "new_revision_id": str(report.new_revision_id),
        "status": report.status,
        "diff_summary": report.diff_summary.__dict__,
        "reprocessed_chunks": [str(item) for item in report.reprocessed_chunks],
        "reused_chunks": [str(item) for item in report.reused_chunks],
        "superseded_claims": [str(item) for item in report.superseded_claims],
        "new_claims": [str(item) for item in report.new_claims],
        "conflict_groups": [
            {
                "conflict_group_id": str(item.conflict_group_id),
                "claim_ids": [str(claim_id) for claim_id in item.claim_ids],
                "classification": item.classification,
                "basis": item.basis,
            }
            for item in report.conflict_groups
        ],
        "stale_artifacts": [{"artifact_id": str(item.artifact_id), "reasons": list(item.reasons)} for item in report.stale_artifacts],
        "warnings": list(report.warnings),
        "errors": list(report.errors),
        "metadata": report.metadata,
    }


def _report_from_metadata(run: KnowledgeUpdateRun) -> KnowledgeUpdateReport:
    data = run.metadata_json["report"]
    return KnowledgeUpdateReport(
        run_id=UUID(data["run_id"]),
        source_id=UUID(data["source_id"]),
        old_revision_id=UUID(data["old_revision_id"]),
        new_revision_id=UUID(data["new_revision_id"]),
        status=JobStatus(data["status"]),
        diff_summary=RevisionDiffSummary(**data["diff_summary"]),
        reprocessed_chunks=tuple(UUID(item) for item in data["reprocessed_chunks"]),
        reused_chunks=tuple(UUID(item) for item in data["reused_chunks"]),
        superseded_claims=tuple(UUID(item) for item in data["superseded_claims"]),
        new_claims=tuple(UUID(item) for item in data["new_claims"]),
        conflict_groups=tuple(
            ConflictGroupResult(
                UUID(item["conflict_group_id"]),
                tuple(UUID(claim_id) for claim_id in item["claim_ids"]),
                item["classification"],
                item["basis"],
            )
            for item in data["conflict_groups"]
        ),
        stale_artifacts=tuple(StaleArtifactResult(UUID(item["artifact_id"]), tuple(item["reasons"])) for item in data["stale_artifacts"]),
        warnings=tuple(data["warnings"]),
        errors=tuple(data["errors"]),
        metadata=dict(data["metadata"]),
    )
