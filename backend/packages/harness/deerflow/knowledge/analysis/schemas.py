from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ANALYZER_NAME = "evidence_grounded_analysis"
PROMPT_VERSION = "1"


class ValidationSeverity(StrEnum):
    WARNING = "warning"
    FIXED = "fixed"
    REJECTED = "rejected"


class ValidationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    error_type: str
    message: str
    severity: ValidationSeverity


class EvidenceCitation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    citation_id: str
    candidate_id: UUID
    evidence_span_id: UUID | None = None
    chunk_id: UUID | None = None
    source_id: UUID | None = None
    revision_id: UUID | None = None
    quoted_text: str
    start_offset: int | None = Field(default=None, ge=0)
    end_offset: int | None = Field(default=None, ge=0)
    direct_evidence: bool = True
    is_context_expansion: bool = False
    page_number: int | None = None
    source_title: str | None = None
    source_uri: str | None = None

    @model_validator(mode="after")
    def offsets_are_ordered(self) -> EvidenceCitation:
        if self.start_offset is not None and self.end_offset is not None and self.end_offset < self.start_offset:
            raise ValueError("end_offset must be greater than or equal to start_offset")
        return self


class SupportedFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    statement: str = Field(min_length=1)
    citations: list[EvidenceCitation] = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("statement")
    @classmethod
    def strip_statement(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("statement must not be blank")
        return stripped


class InferredConclusion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    statement: str = Field(min_length=1)
    based_on_citations: list[EvidenceCitation] = Field(default_factory=list)
    reasoning_summary: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    is_inference: bool = True

    @model_validator(mode="after")
    def must_be_marked_as_inference(self) -> InferredConclusion:
        if self.is_inference is not True:
            raise ValueError("inferred conclusions must be explicitly marked as inference")
        return self


class UnsupportedClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    statement: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    severity: str = Field(min_length=1)


class UnresolvedQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1)
    why_unresolved: str = Field(min_length=1)
    needed_evidence: str = Field(min_length=1)


class SourceSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: UUID | None = None
    title: str | None = None
    uri: str | None = None
    revision_id: UUID | None = None
    summary: str | None = None


class SupportedFactDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    statement: str = Field(min_length=1)
    citation_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class InferredConclusionDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    statement: str = Field(min_length=1)
    based_on_citation_ids: list[str] = Field(default_factory=list)
    reasoning_summary: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    is_inference: bool = True

    @model_validator(mode="after")
    def must_be_marked_as_inference(self) -> InferredConclusionDraft:
        if self.is_inference is not True:
            raise ValueError("inferred conclusions must be explicitly marked as inference")
        return self


class AnalysisModelOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str = Field(min_length=1)
    supported_facts: list[SupportedFactDraft] = Field(default_factory=list)
    inferred_conclusions: list[InferredConclusionDraft] = Field(default_factory=list)
    unsupported_or_insufficient_claims: list[UnsupportedClaim] = Field(default_factory=list)
    unresolved_questions: list[UnresolvedQuestion] = Field(default_factory=list)
    source_summary: str = ""
    confidence: float = Field(ge=0.0, le=1.0)
    warnings: list[str] = Field(default_factory=list)


class AnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    workspace_id: UUID
    query: str = Field(min_length=1)
    messages: list
    prompt_version: str = PROMPT_VERSION


class AnalysisResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    answer: str
    supported_facts: list[SupportedFact]
    inferred_conclusions: list[InferredConclusion]
    unsupported_or_insufficient_claims: list[UnsupportedClaim]
    unresolved_questions: list[UnresolvedQuestion]
    evidence_used: list[EvidenceCitation]
    source_summary: list[SourceSummary]
    confidence: float = Field(ge=0.0, le=1.0)
    warnings: list[str]
    validation_issues: list[ValidationIssue] = Field(default_factory=list)
    generated_at: datetime
    model_identity: str
    prompt_version: str
