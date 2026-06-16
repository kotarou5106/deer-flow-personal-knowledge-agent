from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from uuid import UUID


@dataclass(frozen=True)
class SourceInput:
    kind: str
    value: str
    thread_id: str | None = None
    user_id: str | None = None
    display_name: str | None = None
    media_type: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class NormalizedSource:
    source_type: str
    canonical_uri: str
    display_name: str
    media_type: str | None
    original_metadata: dict[str, object]
    local_path: Path | None = None
    url: str | None = None


@dataclass(frozen=True)
class AcquiredContent:
    raw_bytes: bytes
    media_type: str | None
    source_metadata: dict[str, object]
    captured_at: datetime


@dataclass(frozen=True)
class TextBlock:
    text: str
    section_path: tuple[str, ...] = ()
    page_number: int | None = None
    slide_number: int | None = None
    sheet_name: str | None = None
    row_start: int | None = None
    row_end: int | None = None
    start_offset: int = 0
    end_offset: int = 0


@dataclass(frozen=True)
class ParsedDocument:
    title: str | None
    text_blocks: tuple[TextBlock, ...]
    parser_name: str
    parser_version: str
    warnings: tuple[str, ...] = ()
    metadata: dict[str, object] = field(default_factory=dict)

    @property
    def text(self) -> str:
        return "\n\n".join(block.text for block in self.text_blocks if block.text.strip())


@dataclass(frozen=True)
class ChunkingConfig:
    parent_max_chars: int = 4000
    child_max_chars: int = 900
    child_overlap_chars: int = 120


@dataclass(frozen=True)
class ChunkDraft:
    content: str
    chunk_index: int
    section_path: tuple[str, ...]
    page_number: int | None
    start_offset: int
    end_offset: int
    parent_index: int | None = None


@dataclass(frozen=True)
class IngestionResult:
    job_id: UUID
    source_id: UUID | None
    snapshot_id: UUID | None
    revision_id: UUID | None
    status: str
    deduplicated: bool
    chunk_count: int
    warnings: tuple[str, ...] = ()
