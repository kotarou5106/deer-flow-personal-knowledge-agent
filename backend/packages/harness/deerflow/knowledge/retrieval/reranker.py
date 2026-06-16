from __future__ import annotations

import asyncio
from typing import Protocol
from uuid import UUID

from deerflow.knowledge.retrieval.schemas import RerankOutput, RetrievalCandidate


class RerankerModel(Protocol):
    async def rerank(self, query: str, candidates: list[RetrievalCandidate]) -> RerankOutput: ...


class Reranker:
    def __init__(self, *, model: RerankerModel | None = None, timeout_seconds: float = 15.0) -> None:
        self._model = model
        self._timeout_seconds = timeout_seconds

    async def rerank(self, query: str, candidates: list[RetrievalCandidate]) -> tuple[list[RetrievalCandidate], list[str]]:
        if self._model is None or not candidates:
            return candidates, []
        try:
            output = await asyncio.wait_for(self._model.rerank(query, candidates), timeout=self._timeout_seconds)
            ordered_ids = _validate_rerank_output(output, {candidate.candidate_id for candidate in candidates})
        except Exception as exc:
            return candidates, [f"reranker fallback: {exc}"]
        by_id = {candidate.candidate_id: candidate for candidate in candidates}
        reranked = [by_id[candidate_id] for candidate_id in ordered_ids]
        remaining = [candidate for candidate in candidates if candidate.candidate_id not in set(ordered_ids)]
        result = [*reranked, *remaining]
        for index, candidate in enumerate(result, start=1):
            candidate.final_rank = index
        return result, []


def _validate_rerank_output(output: RerankOutput, valid_ids: set[UUID]) -> list[UUID]:
    seen: set[UUID] = set()
    ordered = sorted(output.scores, key=lambda item: (-item.relevance_score, str(item.candidate_id)))
    result: list[UUID] = []
    for score in ordered:
        if score.candidate_id not in valid_ids:
            raise ValueError(f"reranker returned unknown candidate id: {score.candidate_id}")
        if score.candidate_id in seen:
            raise ValueError(f"reranker returned duplicate candidate id: {score.candidate_id}")
        seen.add(score.candidate_id)
        result.append(score.candidate_id)
    return result
