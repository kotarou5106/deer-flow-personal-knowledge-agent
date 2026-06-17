from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from uuid import UUID

from deerflow.knowledge.enums import JobStatus

UPDATER_NAME = "knowledge_update_service"
UPDATER_VERSION = "1"


class ChunkChangeType(StrEnum):
    UNCHANGED = "unchanged"
    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"
    MOVED = "moved"


class ClaimLifecycleStatus(StrEnum):
    CURRENT_ACTIVE = "current_active"
    SUPERSEDED = "superseded"
    HISTORICAL = "historical"
    PENDING_CONFLICT_REVIEW = "pending_conflict_review"
    INVALID_EVIDENCE_REMOVED = "invalid_evidence_removed"


class ConflictClassification(StrEnum):
    DIRECT_CONTRADICTION = "direct_contradiction"
    TEMPORAL_UPDATE = "temporal_update"
    SCOPE_OR_CONDITION_DIFFERENCE = "scope_or_condition_difference"
    SOURCE_DISAGREEMENT = "source_disagreement"
    POSSIBLE_CONFLICT = "possible_conflict"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


@dataclass(frozen=True)
class ChunkPair:
    old_chunk_id: UUID
    new_chunk_id: UUID
    change_type: ChunkChangeType


@dataclass(frozen=True)
class RevisionDiffSummary:
    unchanged: int
    added: int
    removed: int
    modified: int
    moved: int


@dataclass(frozen=True)
class RevisionDiff:
    old_revision_id: UUID
    new_revision_id: UUID
    unchanged_pairs: tuple[ChunkPair, ...]
    added_chunk_ids: tuple[UUID, ...]
    removed_chunk_ids: tuple[UUID, ...]
    modified_pairs: tuple[ChunkPair, ...]
    moved_pairs: tuple[ChunkPair, ...]
    summary: RevisionDiffSummary


@dataclass(frozen=True)
class IncrementalProcessingPlan:
    reprocess_chunk_ids: tuple[UUID, ...]
    reused_chunk_ids: tuple[UUID, ...]
    removed_chunk_ids: tuple[UUID, ...]


@dataclass(frozen=True)
class ConflictDecision:
    classification: ConflictClassification
    basis: str


@dataclass(frozen=True)
class ConflictGroupResult:
    conflict_group_id: UUID
    claim_ids: tuple[UUID, ...]
    classification: ConflictClassification
    basis: str


@dataclass(frozen=True)
class StaleArtifactResult:
    artifact_id: UUID
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class KnowledgeUpdateReport:
    run_id: UUID
    source_id: UUID
    old_revision_id: UUID
    new_revision_id: UUID
    status: JobStatus
    diff_summary: RevisionDiffSummary
    reprocessed_chunks: tuple[UUID, ...]
    reused_chunks: tuple[UUID, ...]
    superseded_claims: tuple[UUID, ...] = ()
    new_claims: tuple[UUID, ...] = ()
    conflict_groups: tuple[ConflictGroupResult, ...] = ()
    stale_artifacts: tuple[StaleArtifactResult, ...] = ()
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    metadata: dict = field(default_factory=dict)
