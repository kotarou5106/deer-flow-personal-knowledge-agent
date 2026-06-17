from __future__ import annotations

from deerflow.knowledge.analysis.citation_validator import EvidenceIndex, resolve_citations
from deerflow.knowledge.analysis.schemas import (
    AnalysisModelOutput,
    InferredConclusion,
    SupportedFact,
    UnsupportedClaim,
    ValidationIssue,
    ValidationSeverity,
)


class GroundingValidator:
    def validate(self, output: AnalysisModelOutput, evidence_index: EvidenceIndex) -> tuple[list[SupportedFact], list[InferredConclusion], list[UnsupportedClaim], list[ValidationIssue]]:
        issues: list[ValidationIssue] = list(evidence_index.issues)
        supported_facts: list[SupportedFact] = []
        unsupported = list(output.unsupported_or_insufficient_claims)

        for index, fact in enumerate(output.supported_facts):
            citations, citation_issues = resolve_citations(
                fact.citation_ids,
                evidence_index,
                path=f"supported_facts[{index}].citation_ids",
                require_direct_evidence=True,
            )
            issues.extend(citation_issues)
            if any(issue.severity == ValidationSeverity.REJECTED for issue in citation_issues):
                unsupported.append(
                    UnsupportedClaim(
                        statement=fact.statement,
                        reason="Rejected because the factual statement was not grounded in valid direct evidence",
                        severity="high",
                    )
                )
                continue
            supported_facts.append(SupportedFact(statement=fact.statement, citations=citations, confidence=fact.confidence))

        inferred: list[InferredConclusion] = []
        for index, conclusion in enumerate(output.inferred_conclusions):
            citations, citation_issues = resolve_citations(
                conclusion.based_on_citation_ids,
                evidence_index,
                path=f"inferred_conclusions[{index}].based_on_citation_ids",
                require_direct_evidence=False,
            )
            issues.extend(citation_issues)
            if any(issue.error_type == "unknown_citation" for issue in citation_issues):
                unsupported.append(
                    UnsupportedClaim(
                        statement=conclusion.statement,
                        reason="Rejected because the inference referenced unknown evidence",
                        severity="medium",
                    )
                )
                continue
            inferred.append(
                InferredConclusion(
                    statement=conclusion.statement,
                    based_on_citations=citations,
                    reasoning_summary=conclusion.reasoning_summary,
                    confidence=conclusion.confidence,
                    is_inference=True,
                )
            )

        return supported_facts, inferred, unsupported, issues
