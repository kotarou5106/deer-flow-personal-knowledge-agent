from __future__ import annotations

from collections.abc import Awaitable, Callable
from uuid import UUID

from deerflow.knowledge.retrieval.schemas import CandidateType, RetrievalCandidate, RetrievalChannel

ParentLoader = Callable[[UUID, UUID], Awaitable[RetrievalCandidate | None]]


async def expand_parent_context(
    candidates: list[RetrievalCandidate],
    *,
    load_parent: ParentLoader,
    context_budget: int,
) -> list[RetrievalCandidate]:
    expanded: list[RetrievalCandidate] = []
    seen_parent_ids: set[UUID] = set()
    used = 0
    for candidate in candidates:
        expanded.append(candidate)
        used += len(candidate.content)
        parent_id = candidate.metadata.get("parent_chunk_id")
        if not parent_id or candidate.candidate_type != CandidateType.CHUNK:
            continue
        parent_uuid = UUID(str(parent_id))
        if parent_uuid in seen_parent_ids:
            continue
        parent = await load_parent(candidate.workspace_id, parent_uuid)
        if parent is None:
            continue
        if used + len(parent.content) > context_budget:
            continue
        parent.is_context_expansion = True
        parent.direct_evidence = False
        parent.retrieval_channel = RetrievalChannel.LEXICAL
        seen_parent_ids.add(parent_uuid)
        expanded.append(parent)
        used += len(parent.content)
    return expanded
