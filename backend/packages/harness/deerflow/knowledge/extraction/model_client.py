from __future__ import annotations

import asyncio
import re
from typing import Protocol

from pydantic import ValidationError

from deerflow.knowledge.enums import ClaimStance
from deerflow.knowledge.extraction.prompts import build_messages
from deerflow.knowledge.extraction.schemas import ExtractedClaim, ExtractedEntity, ExtractedEvidenceSpan, ModelExtractionRequest, StructuredExtractionOutput
from deerflow.models.factory import create_chat_model


class ExtractionModelNotConfiguredError(RuntimeError):
    pass


class StructuredExtractionModel(Protocol):
    @property
    def model_identity(self) -> str: ...

    async def extract(self, request: ModelExtractionRequest) -> StructuredExtractionOutput: ...


class DeterministicStructuredExtractionModel:
    """Local extraction model for Knowledge update wiring without external APIs."""

    @property
    def model_identity(self) -> str:
        return "deterministic-extraction"

    async def extract(self, request: ModelExtractionRequest) -> StructuredExtractionOutput:
        text = request.chunk_text.strip()
        if not text:
            return StructuredExtractionOutput()

        entities: dict[str, ExtractedEntity] = {}
        claims: list[ExtractedClaim] = []
        for index, (sentence, start) in enumerate(_sentences(text), start=1):
            parsed = _parse_claim(sentence)
            if parsed is None:
                continue
            subject, predicate, obj, stance = parsed
            subject_id = _local_id(subject)
            entities.setdefault(
                subject_id,
                ExtractedEntity(
                    local_id=subject_id,
                    canonical_name=subject,
                    entity_type="concept",
                    aliases=[],
                    confidence=0.82,
                ),
            )
            evidence = ExtractedEvidenceSpan(
                chunk_id=request.chunk_id,
                start_offset=start,
                end_offset=start + len(sentence),
                quoted_text=sentence,
            )
            claims.append(
                ExtractedClaim(
                    local_id=f"claim-{index}",
                    subject_entity_local_id=subject_id,
                    predicate=predicate,
                    object_text=obj,
                    claim_text=sentence,
                    stance=stance,
                    confidence=0.78,
                    evidence_spans=[evidence],
                )
            )
        return StructuredExtractionOutput(entities=list(entities.values()), claims=claims, relations=[])


class LangChainStructuredExtractionModel:
    def __init__(self, *, model_name: str | None = None, timeout_seconds: float = 60.0, max_retries: int = 1) -> None:
        if model_name is None:
            raise ExtractionModelNotConfiguredError("Structured extraction requires an explicit model_name or injected model client")
        self._model_name = model_name
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._model = create_chat_model(model_name, thinking_enabled=False, attach_tracing=True)
        if not hasattr(self._model, "with_structured_output"):
            raise ExtractionModelNotConfiguredError(f"Model {model_name} does not support structured output")
        self._structured_model = self._model.with_structured_output(StructuredExtractionOutput)

    @property
    def model_identity(self) -> str:
        return self._model_name

    async def extract(self, request: ModelExtractionRequest) -> StructuredExtractionOutput:
        messages = build_messages(request)
        last_error: Exception | None = None
        for _ in range(self._max_retries + 1):
            try:
                result = await asyncio.wait_for(self._structured_model.ainvoke(messages), timeout=self._timeout_seconds)
                if isinstance(result, StructuredExtractionOutput):
                    return result
                return StructuredExtractionOutput.model_validate(result)
            except (TimeoutError, ValidationError, ValueError) as exc:
                last_error = exc
        raise RuntimeError(f"Structured extraction model failed: {last_error}") from last_error


def _sentences(text: str) -> list[tuple[str, int]]:
    sentences: list[tuple[str, int]] = []
    start = 0
    for match in re.finditer(r"[^.!?]+[.!?]?", text):
        sentence = match.group(0).strip()
        if sentence:
            sentences.append((sentence, match.start() + len(match.group(0)) - len(match.group(0).lstrip())))
        start = match.end()
    if start < len(text):
        tail = text[start:].strip()
        if tail:
            sentences.append((tail, text.index(tail, start)))
    return sentences


def _parse_claim(sentence: str) -> tuple[str, str, str, ClaimStance] | None:
    stripped = sentence.strip()
    if not stripped:
        return None
    patterns = [
        (r"^(?P<subject>.+?)\s+is\s+not\s+(?P<object>.+?)[.!?]?$", ClaimStance.OPPOSES),
        (r"^(?P<subject>.+?)\s+is\s+(?P<object>.+?)[.!?]?$", ClaimStance.SUPPORTS),
        (r"^(?P<subject>.+?)\s+was\s+not\s+(?P<object>.+?)[.!?]?$", ClaimStance.OPPOSES),
        (r"^(?P<subject>.+?)\s+was\s+(?P<object>.+?)[.!?]?$", ClaimStance.SUPPORTS),
    ]
    for pattern, stance in patterns:
        match = re.match(pattern, stripped, flags=re.IGNORECASE)
        if match is None:
            continue
        subject = _clean_phrase(match.group("subject"))
        obj = _clean_phrase(match.group("object"))
        if not subject or not obj:
            return None
        predicate = _predicate_for_subject(subject)
        normalized_subject = _normalize_subject(subject, predicate)
        return normalized_subject, predicate, obj, stance
    return None


def _clean_phrase(value: str) -> str:
    return value.strip().strip(" .!?")


def _predicate_for_subject(subject: str) -> str:
    lowered = subject.casefold()
    if lowered.endswith(" deadline"):
        return "deadline"
    if lowered.endswith(" model"):
        return "model"
    if lowered.endswith(" launch gate"):
        return "launch_gate"
    if lowered.endswith(" risk"):
        return "risk"
    return "state"


def _normalize_subject(subject: str, predicate: str) -> str:
    lowered = subject.casefold()
    suffixes = {
        "deadline": " deadline",
        "model": " model",
        "launch_gate": " launch gate",
        "risk": " risk",
    }
    suffix = suffixes.get(predicate)
    if suffix and lowered.endswith(suffix):
        return subject[: -len(suffix)].strip()
    return subject


def _local_id(value: str) -> str:
    candidate = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return candidate or "subject"
