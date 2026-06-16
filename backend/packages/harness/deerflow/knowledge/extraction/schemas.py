from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from deerflow.knowledge.enums import ClaimStance, JobStatus

EXTRACTOR_NAME = "structured_knowledge_extraction"
EXTRACTOR_VERSION = "1"


class ValidationSeverity(StrEnum):
    WARNING = "warning"
    FIXED = "fixed"
    REJECTED = "rejected"


class ValidationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    error_type: str
    message: str
    fix_hint: str | None = None
    severity: ValidationSeverity


class ExtractedEvidenceSpan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: UUID
    start_offset: int = Field(ge=0)
    end_offset: int = Field(ge=0)
    quoted_text: str = Field(min_length=1)

    @model_validator(mode="after")
    def offsets_are_ordered(self) -> ExtractedEvidenceSpan:
        if self.end_offset <= self.start_offset:
            raise ValueError("end_offset must be greater than start_offset")
        return self


class ExtractedEntity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    local_id: str = Field(min_length=1)
    canonical_name: str = Field(min_length=1)
    entity_type: str = Field(min_length=1, max_length=64)
    aliases: list[str] = Field(default_factory=list)
    description: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("canonical_name", "entity_type", "local_id")
    @classmethod
    def strip_non_empty(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped

    @field_validator("aliases")
    @classmethod
    def strip_aliases(cls, aliases: list[str]) -> list[str]:
        return [alias.strip() for alias in aliases if alias and alias.strip()]


class ExtractedClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    local_id: str = Field(min_length=1)
    subject_entity_local_id: str = Field(min_length=1)
    predicate: str = Field(min_length=1)
    object_entity_local_id: str | None = None
    object_text: str | None = None
    claim_text: str = Field(min_length=1)
    stance: ClaimStance = ClaimStance.NEUTRAL
    confidence: float = Field(ge=0.0, le=1.0)
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    evidence_spans: list[ExtractedEvidenceSpan] = Field(min_length=1)

    @model_validator(mode="after")
    def object_is_clear(self) -> ExtractedClaim:
        if bool(self.object_entity_local_id) == bool(self.object_text):
            raise ValueError("exactly one of object_entity_local_id or object_text is required")
        if self.valid_from and self.valid_to and self.valid_from > self.valid_to:
            raise ValueError("valid_from must be before valid_to")
        return self


class ExtractedRelation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_entity_local_id: str = Field(min_length=1)
    relation_type: str = Field(min_length=1, max_length=128)
    target_entity_local_id: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_spans: list[ExtractedEvidenceSpan] = Field(min_length=1)

    @model_validator(mode="after")
    def relation_is_not_self_loop(self) -> ExtractedRelation:
        if self.source_entity_local_id == self.target_entity_local_id:
            raise ValueError("relation endpoints must be different local entities")
        return self


class StructuredExtractionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entities: list[ExtractedEntity] = Field(default_factory=list)
    claims: list[ExtractedClaim] = Field(default_factory=list)
    relations: list[ExtractedRelation] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class ChunkText:
    id: UUID
    revision_id: UUID
    workspace_id: UUID
    content: str
    page_number: int | None
    section_path: list[str] = field(default_factory=list)


@dataclass
class ValidatedExtraction:
    output: StructuredExtractionOutput
    issues: list[ValidationIssue] = field(default_factory=list)
    rejected_item_count: int = 0


@dataclass(frozen=True)
class ExtractionResult:
    extraction_run_id: UUID
    revision_id: UUID
    status: JobStatus
    processed_chunk_count: int
    entity_count: int
    claim_count: int
    relation_count: int
    rejected_item_count: int
    warnings: list[str]


class ModelExtractionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: UUID
    revision_id: UUID
    chunk_id: UUID
    chunk_text: str
    page_number: int | None = None
    section_path: list[str] = Field(default_factory=list)


class ModelExtractionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["structured_knowledge_extraction"] = "structured_knowledge_extraction"
    output: StructuredExtractionOutput
