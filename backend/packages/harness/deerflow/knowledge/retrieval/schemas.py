from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CandidateType(StrEnum):
    CHUNK = "chunk"
    ENTITY = "entity"
    CLAIM = "claim"
    RELATION = "relation"
    EVIDENCE = "evidence"


class RetrievalChannel(StrEnum):
    LEXICAL = "lexical"
    VECTOR_CHUNK = "vector_chunk"
    VECTOR_ENTITY = "vector_entity"
    VECTOR_CLAIM = "vector_claim"
    GRAPH = "graph"


class DateRange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: datetime | None = None
    end: datetime | None = None

    @model_validator(mode="after")
    def ordered(self) -> DateRange:
        if self.start and self.end and self.start > self.end:
            raise ValueError("date_range.start must be before date_range.end")
        return self


class QuerySpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query_text: str = Field(min_length=1)
    keywords: list[str] = Field(default_factory=list)
    entity_hints: list[str] = Field(default_factory=list)
    source_ids: list[UUID] = Field(default_factory=list)
    collection_ids: list[UUID] = Field(default_factory=list)
    date_range: DateRange | None = None
    content_types: list[str] = Field(default_factory=list)
    top_k: int = Field(default=10, ge=1, le=100)
    graph_depth: int = Field(default=1, ge=0, le=2)

    @field_validator("query_text")
    @classmethod
    def strip_query(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("query_text must not be blank")
        return stripped

    @field_validator("keywords", "entity_hints", "content_types")
    @classmethod
    def strip_values(cls, values: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            stripped = value.strip()
            if not stripped:
                continue
            key = stripped.casefold()
            if key in seen:
                continue
            seen.add(key)
            result.append(stripped)
        return result


class Provenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: UUID | None = None
    snapshot_id: UUID | None = None
    revision_id: UUID | None = None
    chunk_id: UUID | None = None
    evidence_span_id: UUID | None = None
    page_number: int | None = None
    section_path: list[str] = Field(default_factory=list)
    start_offset: int | None = None
    end_offset: int | None = None


@dataclass
class RetrievalCandidate:
    candidate_type: CandidateType
    candidate_id: UUID
    workspace_id: UUID
    source_id: UUID | None
    revision_id: UUID | None
    chunk_id: UUID | None
    content: str
    retrieval_channel: RetrievalChannel
    raw_score: float
    rank: int
    metadata: dict = field(default_factory=dict)
    provenance: Provenance = field(default_factory=Provenance)
    channel_scores: dict[str, dict[str, float | int]] = field(default_factory=dict)
    fused_score: float = 0.0
    final_rank: int | None = None
    is_context_expansion: bool = False
    direct_evidence: bool = True

    @property
    def stable_key(self) -> tuple[str, UUID]:
        return (self.candidate_type.value, self.candidate_id)


@dataclass(frozen=True)
class RRFConfig:
    k: int = 60
    channel_weights: dict[str, float] = field(default_factory=dict)


class RerankScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: UUID
    relevance_score: float = Field(ge=0.0, le=1.0)


class RerankOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scores: list[RerankScore]


@dataclass
class EvidenceContextPack:
    query: str
    query_spec: QuerySpec
    retrieved_chunks: list[RetrievalCandidate]
    entities: list[RetrievalCandidate]
    claims: list[RetrievalCandidate]
    relations: list[RetrievalCandidate]
    evidence_spans: list[RetrievalCandidate]
    sources: list[dict]
    channel_scores: dict[str, dict[str, float | int]]
    final_rank: list[tuple[str, UUID]]
    context_budget: int
    warnings: list[str] = field(default_factory=list)
