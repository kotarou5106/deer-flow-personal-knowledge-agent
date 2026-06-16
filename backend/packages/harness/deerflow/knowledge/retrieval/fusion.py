from __future__ import annotations

from deerflow.knowledge.retrieval.schemas import RetrievalCandidate, RRFConfig


def reciprocal_rank_fusion(candidates: list[RetrievalCandidate], config: RRFConfig | None = None) -> list[RetrievalCandidate]:
    cfg = config or RRFConfig()
    merged: dict[tuple[str, object], RetrievalCandidate] = {}
    for candidate in candidates:
        key = candidate.stable_key
        channel = candidate.retrieval_channel.value
        weight = cfg.channel_weights.get(channel, 1.0)
        contribution = weight / (cfg.k + candidate.rank)
        if key not in merged:
            candidate.channel_scores = {}
            candidate.fused_score = 0.0
            merged[key] = candidate
        target = merged[key]
        target.fused_score += contribution
        existing = target.channel_scores.get(channel)
        if existing is None or candidate.rank < int(existing["rank"]):
            target.channel_scores[channel] = {"rank": candidate.rank, "raw_score": candidate.raw_score, "rrf": contribution}
        if candidate.content and len(candidate.content) > len(target.content):
            target.content = candidate.content
    ordered = sorted(
        merged.values(),
        key=lambda item: (-item.fused_score, item.candidate_type.value, str(item.candidate_id)),
    )
    for index, candidate in enumerate(ordered, start=1):
        candidate.final_rank = index
    return ordered
