from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID

from deerflow.knowledge.analysis.schemas import EvidenceCitation, ValidationIssue, ValidationSeverity
from deerflow.knowledge.retrieval.schemas import EvidenceContextPack, RetrievalCandidate


@dataclass(frozen=True)
class EvidenceIndex:
    citations: list[EvidenceCitation]
    by_id: dict[str, EvidenceCitation]
    issues: list[ValidationIssue]


def build_evidence_index(pack: EvidenceContextPack, workspace_id: UUID) -> EvidenceIndex:
    candidates = _ordered_candidates(pack)
    citations: list[EvidenceCitation] = []
    issues: list[ValidationIssue] = []
    for index, candidate in enumerate(candidates, start=1):
        citation_id = f"C{index}"
        if candidate.workspace_id != workspace_id:
            issues.append(
                ValidationIssue(
                    path=f"evidence[{index}]",
                    error_type="workspace_mismatch",
                    message="Evidence candidate belongs to a different workspace",
                    severity=ValidationSeverity.REJECTED,
                )
            )
            continue
        quote = _quote_for(candidate)
        citations.append(
            EvidenceCitation(
                citation_id=citation_id,
                candidate_id=candidate.candidate_id,
                evidence_span_id=candidate.provenance.evidence_span_id,
                chunk_id=candidate.chunk_id or candidate.provenance.chunk_id,
                source_id=candidate.source_id or candidate.provenance.source_id,
                revision_id=candidate.revision_id or candidate.provenance.revision_id,
                quoted_text=quote,
                start_offset=candidate.provenance.start_offset,
                end_offset=candidate.provenance.end_offset,
                direct_evidence=candidate.direct_evidence,
                is_context_expansion=candidate.is_context_expansion,
                page_number=candidate.provenance.page_number,
                source_title=_metadata_text(candidate, "source_title"),
                source_uri=_metadata_text(candidate, "source_uri"),
            )
        )
    return EvidenceIndex(citations=citations, by_id={citation.citation_id: citation for citation in citations}, issues=issues)


def resolve_citations(
    citation_ids: list[str],
    index: EvidenceIndex,
    *,
    path: str,
    require_direct_evidence: bool,
) -> tuple[list[EvidenceCitation], list[ValidationIssue]]:
    issues: list[ValidationIssue] = []
    if not citation_ids:
        return [], [
            ValidationIssue(
                path=path,
                error_type="missing_citation",
                message="Factual statements must include at least one citation",
                severity=ValidationSeverity.REJECTED,
            )
        ]
    citations: list[EvidenceCitation] = []
    seen: set[str] = set()
    for citation_id in citation_ids:
        normalized = citation_id.strip()
        if normalized in seen:
            continue
        seen.add(normalized)
        citation = index.by_id.get(normalized)
        if citation is None:
            issues.append(
                ValidationIssue(
                    path=path,
                    error_type="unknown_citation",
                    message=f"Citation {normalized} is not present in the EvidenceContextPack",
                    severity=ValidationSeverity.REJECTED,
                )
            )
            continue
        citations.append(citation)
    if require_direct_evidence and citations and not any(citation.direct_evidence and not citation.is_context_expansion for citation in citations):
        issues.append(
            ValidationIssue(
                path=path,
                error_type="parent_only_fact",
                message="Parent context can assist analysis but cannot by itself support a factual statement",
                severity=ValidationSeverity.REJECTED,
            )
        )
    return citations, issues


def validate_quote(citation: EvidenceCitation, expected_quote: str | None) -> bool:
    if expected_quote is None:
        return True
    return _normalize_space(citation.quoted_text) == _normalize_space(expected_quote)


def _ordered_candidates(pack: EvidenceContextPack) -> list[RetrievalCandidate]:
    by_key = {(candidate.candidate_type.value, candidate.candidate_id): candidate for candidate in _all_candidates(pack)}
    ordered: list[RetrievalCandidate] = []
    seen: set[tuple[str, UUID]] = set()
    for key in pack.final_rank:
        candidate = by_key.get(key)
        if candidate is None or key in seen:
            continue
        seen.add(key)
        ordered.append(candidate)
    for candidate in _all_candidates(pack):
        key = (candidate.candidate_type.value, candidate.candidate_id)
        if key in seen:
            continue
        seen.add(key)
        ordered.append(candidate)
    return ordered


def _all_candidates(pack: EvidenceContextPack) -> list[RetrievalCandidate]:
    return [*pack.retrieved_chunks, *pack.claims, *pack.relations, *pack.evidence_spans, *pack.entities]


def _quote_for(candidate: RetrievalCandidate) -> str:
    start = candidate.provenance.start_offset
    end = candidate.provenance.end_offset
    if start is not None and end is not None and 0 <= start <= end <= len(candidate.content):
        return candidate.content[start:end] or candidate.content
    return candidate.content


def _metadata_text(candidate: RetrievalCandidate, key: str) -> str | None:
    value = candidate.metadata.get(key)
    return str(value) if value is not None else None


def _normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()
