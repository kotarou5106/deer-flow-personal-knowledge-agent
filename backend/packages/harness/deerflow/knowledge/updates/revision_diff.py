from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from uuid import UUID

from deerflow.knowledge.models import Chunk, DocumentRevision
from deerflow.knowledge.updates.schemas import ChunkChangeType, ChunkPair, RevisionDiff, RevisionDiffSummary


@dataclass(frozen=True)
class _ChunkFingerprint:
    chunk_id: UUID
    content_hash: str
    structure_key: tuple
    match_key: tuple


def diff_revisions(old_revision: DocumentRevision, new_revision: DocumentRevision, old_chunks: Iterable[Chunk], new_chunks: Iterable[Chunk]) -> RevisionDiff:
    if old_revision.workspace_id != new_revision.workspace_id:
        raise ValueError("Cannot diff revisions across workspaces")
    if old_revision.source_id != new_revision.source_id:
        raise ValueError("Cannot diff revisions from different sources")
    if old_revision.id == new_revision.id:
        raise ValueError("Old and new revisions must be distinct")

    old_fingerprints = [_fingerprint(chunk) for chunk in old_chunks if chunk.parent_chunk_id is not None]
    new_fingerprints = [_fingerprint(chunk) for chunk in new_chunks if chunk.parent_chunk_id is not None]
    if not old_fingerprints:
        old_fingerprints = [_fingerprint(chunk) for chunk in old_chunks]
    if not new_fingerprints:
        new_fingerprints = [_fingerprint(chunk) for chunk in new_chunks]

    unmatched_old = {item.chunk_id: item for item in old_fingerprints}
    unmatched_new = {item.chunk_id: item for item in new_fingerprints}

    unchanged = _pair_exact(unmatched_old, unmatched_new, ChunkChangeType.UNCHANGED)
    moved = _pair_by_content(unmatched_old, unmatched_new)
    modified = _pair_by_structure(unmatched_old, unmatched_new)

    added = tuple(sorted(unmatched_new, key=str))
    removed = tuple(sorted(unmatched_old, key=str))
    summary = RevisionDiffSummary(
        unchanged=len(unchanged),
        added=len(added),
        removed=len(removed),
        modified=len(modified),
        moved=len(moved),
    )
    return RevisionDiff(
        old_revision_id=old_revision.id,
        new_revision_id=new_revision.id,
        unchanged_pairs=tuple(unchanged),
        added_chunk_ids=added,
        removed_chunk_ids=removed,
        modified_pairs=tuple(modified),
        moved_pairs=tuple(moved),
        summary=summary,
    )


def _fingerprint(chunk: Chunk) -> _ChunkFingerprint:
    content_hash = _content_hash(chunk)
    structure_key = (
        tuple(str(part) for part in (chunk.section_path or [])),
        chunk.page_number,
        chunk.start_offset,
        chunk.end_offset,
        chunk.chunk_index,
    )
    match_key = (
        tuple(str(part) for part in (chunk.section_path or [])),
        chunk.page_number,
        chunk.chunk_index,
    )
    return _ChunkFingerprint(chunk.id, content_hash, structure_key, match_key)


def _content_hash(chunk: Chunk) -> str:
    metadata = chunk.metadata_json if hasattr(chunk, "metadata_json") else None
    if metadata and metadata.get("content_hash"):
        return str(metadata["content_hash"])
    return hashlib.sha256(chunk.content.encode("utf-8")).hexdigest()


def _pair_exact(
    unmatched_old: dict[UUID, _ChunkFingerprint],
    unmatched_new: dict[UUID, _ChunkFingerprint],
    change_type: ChunkChangeType,
) -> list[ChunkPair]:
    old_by_key: dict[tuple[str, tuple], list[_ChunkFingerprint]] = defaultdict(list)
    for old in unmatched_old.values():
        old_by_key[(old.content_hash, old.structure_key)].append(old)

    pairs: list[ChunkPair] = []
    for new in sorted(list(unmatched_new.values()), key=lambda item: (item.structure_key, str(item.chunk_id))):
        matches = old_by_key.get((new.content_hash, new.structure_key), [])
        if not matches:
            continue
        old = sorted(matches, key=lambda item: str(item.chunk_id))[0]
        matches.remove(old)
        pairs.append(ChunkPair(old.chunk_id, new.chunk_id, change_type))
        unmatched_old.pop(old.chunk_id, None)
        unmatched_new.pop(new.chunk_id, None)
    return pairs


def _pair_by_content(unmatched_old: dict[UUID, _ChunkFingerprint], unmatched_new: dict[UUID, _ChunkFingerprint]) -> list[ChunkPair]:
    old_by_hash: dict[str, list[_ChunkFingerprint]] = defaultdict(list)
    for old in unmatched_old.values():
        old_by_hash[old.content_hash].append(old)

    pairs: list[ChunkPair] = []
    for new in sorted(list(unmatched_new.values()), key=lambda item: (item.structure_key, str(item.chunk_id))):
        matches = old_by_hash.get(new.content_hash, [])
        if not matches:
            continue
        old = sorted(matches, key=lambda item: (item.structure_key, str(item.chunk_id)))[0]
        matches.remove(old)
        pairs.append(ChunkPair(old.chunk_id, new.chunk_id, ChunkChangeType.MOVED))
        unmatched_old.pop(old.chunk_id, None)
        unmatched_new.pop(new.chunk_id, None)
    return pairs


def _pair_by_structure(unmatched_old: dict[UUID, _ChunkFingerprint], unmatched_new: dict[UUID, _ChunkFingerprint]) -> list[ChunkPair]:
    old_by_match: dict[tuple, list[_ChunkFingerprint]] = defaultdict(list)
    for old in unmatched_old.values():
        old_by_match[old.match_key].append(old)

    pairs: list[ChunkPair] = []
    for new in sorted(list(unmatched_new.values()), key=lambda item: (item.match_key, str(item.chunk_id))):
        matches = old_by_match.get(new.match_key, [])
        if not matches:
            continue
        old = sorted(matches, key=lambda item: str(item.chunk_id))[0]
        matches.remove(old)
        pairs.append(ChunkPair(old.chunk_id, new.chunk_id, ChunkChangeType.MODIFIED))
        unmatched_old.pop(old.chunk_id, None)
        unmatched_new.pop(new.chunk_id, None)
    return pairs
