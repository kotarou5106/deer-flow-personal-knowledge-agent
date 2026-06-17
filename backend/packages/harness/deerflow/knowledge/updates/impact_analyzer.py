from __future__ import annotations

from deerflow.knowledge.updates.schemas import IncrementalProcessingPlan, RevisionDiff


def build_incremental_processing_plan(diff: RevisionDiff) -> IncrementalProcessingPlan:
    reprocess = tuple(
        sorted(
            [
                *diff.added_chunk_ids,
                *(pair.new_chunk_id for pair in diff.modified_pairs),
            ],
            key=str,
        )
    )
    reused = tuple(
        sorted(
            [
                *(pair.new_chunk_id for pair in diff.unchanged_pairs),
                *(pair.new_chunk_id for pair in diff.moved_pairs),
            ],
            key=str,
        )
    )
    return IncrementalProcessingPlan(
        reprocess_chunk_ids=reprocess,
        reused_chunk_ids=reused,
        removed_chunk_ids=tuple(sorted(diff.removed_chunk_ids, key=str)),
    )
