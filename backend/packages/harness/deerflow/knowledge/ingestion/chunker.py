from __future__ import annotations

from deerflow.knowledge.ingestion.models import ChunkDraft, ChunkingConfig, ParsedDocument, TextBlock

CHUNKER_NAME = "parent_child_chunker"
CHUNKER_VERSION = "1"


def _split_text(text: str, max_chars: int, overlap: int) -> list[tuple[str, int, int]]:
    normalized = text.strip()
    if len(normalized) <= max_chars:
        return [(normalized, 0, len(normalized))]
    parts: list[tuple[str, int, int]] = []
    start = 0
    while start < len(normalized):
        end = min(len(normalized), start + max_chars)
        if end < len(normalized):
            boundary = max(normalized.rfind("\n", start, end), normalized.rfind(". ", start, end), normalized.rfind(" ", start, end))
            if boundary > start + max_chars // 2:
                end = boundary + 1
        piece = normalized[start:end].strip()
        if piece:
            leading = len(normalized[start:end]) - len(normalized[start:end].lstrip())
            trailing_end = end - (len(normalized[start:end]) - len(normalized[start:end].rstrip()))
            parts.append((piece, start + leading, trailing_end))
        if end >= len(normalized):
            break
        start = max(end - overlap, start + 1)
    return parts


def _group_key(block: TextBlock) -> tuple:
    return (block.section_path, block.page_number, block.slide_number, block.sheet_name)


def _group_blocks(blocks: tuple[TextBlock, ...]) -> list[list[TextBlock]]:
    groups: list[list[TextBlock]] = []
    current: list[TextBlock] = []
    current_key: tuple | None = None
    for block in blocks:
        key = _group_key(block)
        if current and key != current_key:
            groups.append(current)
            current = []
        current.append(block)
        current_key = key
    if current:
        groups.append(current)
    return groups


class ParentChildChunker:
    def __init__(self, config: ChunkingConfig | None = None) -> None:
        self.config = config or ChunkingConfig()

    def chunk(self, document: ParsedDocument) -> list[ChunkDraft]:
        drafts: list[ChunkDraft] = []
        for group in _group_blocks(document.text_blocks):
            group_text = "\n\n".join(block.text.strip() for block in group if block.text.strip())
            if not group_text:
                continue
            first = group[0]
            base_start = first.start_offset
            for parent_text, parent_rel_start, parent_rel_end in _split_text(group_text, self.config.parent_max_chars, 0):
                parent_index = len(drafts)
                parent_start = base_start + parent_rel_start
                parent = ChunkDraft(
                    content=parent_text,
                    chunk_index=parent_index,
                    section_path=first.section_path,
                    page_number=first.page_number,
                    start_offset=parent_start,
                    end_offset=base_start + parent_rel_end,
                    parent_index=None,
                )
                drafts.append(parent)
                for child_text, child_rel_start, child_rel_end in _split_text(parent_text, self.config.child_max_chars, self.config.child_overlap_chars):
                    drafts.append(
                        ChunkDraft(
                            content=child_text,
                            chunk_index=len(drafts),
                            section_path=first.section_path,
                            page_number=first.page_number,
                            start_offset=parent_start + child_rel_start,
                            end_offset=parent_start + child_rel_end,
                            parent_index=parent_index,
                        )
                    )
        return drafts
