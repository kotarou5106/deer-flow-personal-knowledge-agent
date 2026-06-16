from __future__ import annotations

from deerflow.knowledge.retrieval.schemas import CandidateType, EvidenceContextPack, QuerySpec, RetrievalCandidate


def build_context_pack(
    *,
    query_spec: QuerySpec,
    candidates: list[RetrievalCandidate],
    context_budget: int,
    warnings: list[str] | None = None,
) -> EvidenceContextPack:
    included: list[RetrievalCandidate] = []
    used = 0
    pack_warnings = list(warnings or [])
    for candidate in candidates:
        cost = len(candidate.content)
        if included and used + cost > context_budget:
            pack_warnings.append("context budget reached; lower-ranked candidates were omitted")
            break
        included.append(candidate)
        used += cost
    return EvidenceContextPack(
        query=query_spec.query_text,
        query_spec=query_spec,
        retrieved_chunks=[item for item in included if item.candidate_type == CandidateType.CHUNK],
        entities=[item for item in included if item.candidate_type == CandidateType.ENTITY],
        claims=[item for item in included if item.candidate_type == CandidateType.CLAIM],
        relations=[item for item in included if item.candidate_type == CandidateType.RELATION],
        evidence_spans=[item for item in included if item.candidate_type == CandidateType.EVIDENCE],
        sources=_sources(included),
        channel_scores={str(item.candidate_id): item.channel_scores for item in included},
        final_rank=[(item.candidate_type.value, item.candidate_id) for item in included],
        context_budget=context_budget,
        warnings=pack_warnings,
    )


def _sources(candidates: list[RetrievalCandidate]) -> list[dict]:
    seen = set()
    result = []
    for candidate in candidates:
        source_id = candidate.source_id or candidate.provenance.source_id
        if source_id is None or source_id in seen:
            continue
        seen.add(source_id)
        result.append({"source_id": str(source_id)})
    return result
