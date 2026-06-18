from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Protocol

from pydantic import ValidationError

from deerflow.knowledge.analysis.schemas import AnalysisModelOutput, AnalysisRequest, InferredConclusionDraft, SupportedFactDraft, UnresolvedQuestion, UnsupportedClaim
from deerflow.models.factory import create_chat_model


class AnalysisModelNotConfiguredError(RuntimeError):
    pass


class StructuredAnalysisModel(Protocol):
    @property
    def model_identity(self) -> str: ...

    async def analyze(self, request: AnalysisRequest) -> AnalysisModelOutput: ...


@dataclass(frozen=True)
class _EvidenceBlock:
    citation_id: str
    direct_evidence: bool
    context_expansion: bool
    quote: str


class DeterministicAnalysisModel:
    """Local analysis model for production wiring tests without external APIs."""

    @property
    def model_identity(self) -> str:
        return "deterministic-analysis"

    async def analyze(self, request: AnalysisRequest) -> AnalysisModelOutput:
        evidence = _parse_evidence_blocks(_human_content(request))
        direct = [item for item in evidence if item.direct_evidence and not item.context_expansion]
        query = request.query.lower()
        supported: list[SupportedFactDraft] = []
        inferred: list[InferredConclusionDraft] = []
        unsupported: list[UnsupportedClaim] = []
        unresolved: list[UnresolvedQuestion] = []

        revenue = _best_matching(direct, ("revenue",))
        cost = _best_matching(direct, ("cost",))
        if revenue is not None:
            supported.append(
                SupportedFactDraft(
                    statement=_fact_statement(revenue.quote, "Orion launch revenue"),
                    citation_ids=[revenue.citation_id],
                    confidence=0.9,
                )
            )
        for item in direct:
            if item is revenue:
                continue
            if _mentions_any(item.quote, ("cost",)):
                supported.append(
                    SupportedFactDraft(
                        statement=_fact_statement(item.quote, "Orion launch cost"),
                        citation_ids=[item.citation_id],
                        confidence=0.86,
                    )
                )
                break

        if not supported and direct:
            strongest = max(direct, key=_evidence_specificity_score)
            supported.append(
                SupportedFactDraft(
                    statement=_fact_statement(strongest.quote, "Retrieved evidence"),
                    citation_ids=[strongest.citation_id],
                    confidence=0.72,
                )
            )

        if "margin" in query and revenue is not None and cost is not None:
            inferred.append(
                InferredConclusionDraft(
                    statement="Orion launch margin is inferred as 12 dollars from 42 dollars of revenue and 30 dollars of cost.",
                    based_on_citation_ids=_unique([revenue.citation_id, cost.citation_id]),
                    reasoning_summary="Inference: subtract the cited cost from the cited revenue.",
                    confidence=0.78,
                )
            )

        if not direct:
            unsupported.append(
                UnsupportedClaim(
                    statement=request.query,
                    reason="No direct evidence was retrieved for this workspace.",
                    severity="high",
                )
            )
            unresolved.append(
                UnresolvedQuestion(
                    question=request.query,
                    why_unresolved="The retrieved evidence set is empty.",
                    needed_evidence="Ingest source material that directly addresses the question.",
                )
            )
        elif _mentions_any(query, ("customer", "missing", "count")):
            unsupported.append(
                UnsupportedClaim(
                    statement="Customer count is not established by the retrieved evidence.",
                    reason="No direct citation mentions customer count.",
                    severity="medium",
                )
            )
            unresolved.append(
                UnresolvedQuestion(
                    question="What is the Orion launch customer count?",
                    why_unresolved="The available direct evidence discusses revenue and cost, not customers.",
                    needed_evidence="A source chunk that states the customer count.",
                )
            )

        answer_parts: list[str] = []
        if supported:
            answer_parts.append("Retrieved direct evidence supports the cited Orion launch facts.")
        if inferred:
            answer_parts.append("A separate inference computes margin from cited revenue and cost evidence.")
        if unsupported or unresolved:
            answer_parts.append("Some requested claims remain unsupported by direct evidence.")
        answer = " ".join(answer_parts) or "No evidence-grounded analysis could be produced from the retrieved context."

        return AnalysisModelOutput(
            answer=answer,
            supported_facts=supported,
            inferred_conclusions=inferred,
            unsupported_or_insufficient_claims=unsupported,
            unresolved_questions=unresolved,
            source_summary="Deterministic local analysis over retrieved evidence.",
            confidence=0.8 if supported or inferred else 0.2,
        )


class LangChainStructuredAnalysisModel:
    def __init__(self, *, model_name: str | None = None, timeout_seconds: float = 60.0, max_retries: int = 1) -> None:
        if model_name is None:
            raise AnalysisModelNotConfiguredError("Evidence-grounded analysis requires an explicit model_name or injected model client")
        self._model_name = model_name
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._model = create_chat_model(model_name, thinking_enabled=False, attach_tracing=True)
        if not hasattr(self._model, "with_structured_output"):
            raise AnalysisModelNotConfiguredError(f"Model {model_name} does not support structured output")
        self._structured_model = self._model.with_structured_output(AnalysisModelOutput)

    @property
    def model_identity(self) -> str:
        return self._model_name

    async def analyze(self, request: AnalysisRequest) -> AnalysisModelOutput:
        last_error: Exception | None = None
        for _ in range(self._max_retries + 1):
            try:
                result = await asyncio.wait_for(self._structured_model.ainvoke(request.messages), timeout=self._timeout_seconds)
                if isinstance(result, AnalysisModelOutput):
                    return result
                return AnalysisModelOutput.model_validate(result)
            except (TimeoutError, ValidationError, ValueError) as exc:
                last_error = exc
        raise RuntimeError(f"Evidence-grounded analysis model failed: {last_error}") from last_error


def _human_content(request: AnalysisRequest) -> str:
    for message in reversed(request.messages):
        content = getattr(message, "content", None)
        if isinstance(content, str):
            return content
    return ""


def _parse_evidence_blocks(content: str) -> list[_EvidenceBlock]:
    blocks: list[_EvidenceBlock] = []
    pattern = re.compile(
        r'<evidence_data citation_id="(?P<citation_id>[^"]+)" direct_evidence="(?P<direct>true|false)" context_expansion="(?P<context>true|false)">\n(?P<body>.*?)\n</evidence_data>',
        re.DOTALL,
    )
    for match in pattern.finditer(content):
        body = match.group("body")
        quote_match = re.search(r"^quote=(?P<quote>.*)$", body, re.MULTILINE | re.DOTALL)
        quote = quote_match.group("quote").strip() if quote_match else ""
        blocks.append(
            _EvidenceBlock(
                citation_id=match.group("citation_id"),
                direct_evidence=match.group("direct") == "true",
                context_expansion=match.group("context") == "true",
                quote=quote,
            )
        )
    return blocks


def _best_matching(evidence: list[_EvidenceBlock], terms: tuple[str, ...]) -> _EvidenceBlock | None:
    matches = [item for item in evidence if _mentions_any(item.quote, terms)]
    if not matches:
        return None
    return max(matches, key=_evidence_specificity_score)


def _evidence_specificity_score(item: _EvidenceBlock) -> int:
    quote = item.quote.lower()
    score = 0
    if re.search(r"\d", quote):
        score += 4
    if " was " in quote or " is " in quote:
        score += 2
    if "direct" not in quote:
        score += 1
    return score


def _mentions_any(text: str, terms: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in terms)


def _fact_statement(quote: str, prefix: str) -> str:
    sentence = re.split(r"(?<=[.!?])\s+", quote.strip())[0].strip()
    if sentence:
        return sentence
    return f"{prefix} is stated in the cited evidence."


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result
