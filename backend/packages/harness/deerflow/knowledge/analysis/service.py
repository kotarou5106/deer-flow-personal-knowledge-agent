from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from deerflow.knowledge.analysis.citation_validator import build_evidence_index
from deerflow.knowledge.analysis.grounding_validator import GroundingValidator
from deerflow.knowledge.analysis.model_client import LangChainStructuredAnalysisModel, StructuredAnalysisModel
from deerflow.knowledge.analysis.prompts import PROMPT_VERSION, build_messages
from deerflow.knowledge.analysis.schemas import (
    AnalysisRequest,
    AnalysisResult,
    SourceSummary,
    UnsupportedClaim,
    ValidationIssue,
)
from deerflow.knowledge.retrieval.schemas import EvidenceContextPack


class AnalysisService:
    def __init__(
        self,
        *,
        model: StructuredAnalysisModel | None = None,
        model_name: str | None = None,
        validator: GroundingValidator | None = None,
    ) -> None:
        self._model = model or (LangChainStructuredAnalysisModel(model_name=model_name) if model_name else None)
        self._validator = validator or GroundingValidator()

    async def analyze(
        self,
        *,
        workspace_id: UUID,
        query: str,
        evidence_context_pack: EvidenceContextPack,
        context_budget: int | None = None,
    ) -> AnalysisResult:
        evidence_index = build_evidence_index(evidence_context_pack, workspace_id)
        prompt_budget = context_budget or evidence_context_pack.context_budget
        messages, prompt_warnings = build_messages(query=query, evidence_index=evidence_index, context_budget=prompt_budget)
        if self._model is None:
            return _fallback_result(
                query=query,
                evidence_context_pack=evidence_context_pack,
                evidence_issues=evidence_index.issues,
                warnings=[*prompt_warnings, "No analysis model configured; returned evidence summary without generated conclusions"],
            )

        output = await self._model.analyze(
            AnalysisRequest(
                workspace_id=workspace_id,
                query=query,
                messages=messages,
                prompt_version=PROMPT_VERSION,
            )
        )
        supported, inferred, unsupported, validation_issues = self._validator.validate(output, evidence_index)
        evidence_used = _unique_citations([citation for fact in supported for citation in fact.citations] + [citation for conclusion in inferred for citation in conclusion.based_on_citations])
        answer = output.answer
        if not supported and unsupported:
            answer = "The retrieved evidence is insufficient to support a factual answer."
        return AnalysisResult(
            query=query,
            answer=answer,
            supported_facts=supported,
            inferred_conclusions=inferred,
            unsupported_or_insufficient_claims=unsupported,
            unresolved_questions=output.unresolved_questions,
            evidence_used=evidence_used,
            source_summary=_source_summary(evidence_context_pack, evidence_used, output.source_summary),
            confidence=output.confidence if supported or inferred else min(output.confidence, 0.2),
            warnings=[*evidence_context_pack.warnings, *prompt_warnings, *output.warnings],
            validation_issues=validation_issues,
            generated_at=datetime.now(UTC),
            model_identity=self._model.model_identity,
            prompt_version=PROMPT_VERSION,
        )


def _fallback_result(
    *,
    query: str,
    evidence_context_pack: EvidenceContextPack,
    evidence_issues: list[ValidationIssue],
    warnings: list[str],
) -> AnalysisResult:
    if evidence_context_pack.sources:
        answer = f"Retrieved {len(evidence_context_pack.sources)} source(s), but no analysis model is configured to generate conclusions."
    else:
        answer = "No evidence was available, and no analysis model is configured to generate conclusions."
    return AnalysisResult(
        query=query,
        answer=answer,
        supported_facts=[],
        inferred_conclusions=[],
        unsupported_or_insufficient_claims=[
            UnsupportedClaim(
                statement="A full evidence-grounded answer was not generated.",
                reason="No analysis model was configured; deterministic fallback cannot infer facts",
                severity="medium",
            )
        ],
        unresolved_questions=[],
        evidence_used=[],
        source_summary=_source_summary(evidence_context_pack, [], "Fallback source summary only"),
        confidence=0.0,
        warnings=warnings,
        validation_issues=evidence_issues,
        generated_at=datetime.now(UTC),
        model_identity="deterministic-fallback",
        prompt_version=PROMPT_VERSION,
    )


def _source_summary(pack: EvidenceContextPack, evidence_used: list, summary: str) -> list[SourceSummary]:
    by_source = {str(citation.source_id): citation for citation in evidence_used if citation.source_id is not None}
    result: list[SourceSummary] = []
    seen: set[str] = set()
    for source in pack.sources:
        source_id_text = str(source.get("source_id") or "")
        if not source_id_text or source_id_text in seen:
            continue
        seen.add(source_id_text)
        citation = by_source.get(source_id_text)
        result.append(
            SourceSummary(
                source_id=citation.source_id if citation else None,
                title=str(source.get("title")) if source.get("title") is not None else (citation.source_title if citation else None),
                uri=str(source.get("uri")) if source.get("uri") is not None else (citation.source_uri if citation else None),
                revision_id=citation.revision_id if citation else None,
                summary=summary,
            )
        )
    return result


def _unique_citations(citations):
    seen = set()
    result = []
    for citation in citations:
        if citation.citation_id in seen:
            continue
        seen.add(citation.citation_id)
        result.append(citation)
    return result
