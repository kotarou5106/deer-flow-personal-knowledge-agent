from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from deerflow.knowledge.models import Chunk
from deerflow.knowledge.retrieval.indexing import IndexingService, sha256_text
from deerflow.knowledge.retrieval.vector import cosine_similarity


class FakeEmbeddingModel:
    model_identity = "fake-embedding"
    dimension = 3

    def __init__(self) -> None:
        self.calls = 0

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        return [[float(len(text)), 1.0, 0.5] for text in texts]


@pytest.mark.asyncio
async def test_embedding_indexing_skips_same_content_model_and_dimension() -> None:
    model = FakeEmbeddingModel()
    service = IndexingService(lambda: None, embedding_model=model)
    chunk = Chunk(
        workspace_id=uuid4(),
        revision_id=uuid4(),
        chunk_index=0,
        content="same content",
        token_count=2,
        section_path=[],
        start_offset=0,
        end_offset=12,
        embedding=[12.0, 1.0, 0.5],
        embedding_model=model.model_identity,
        embedding_dimension=model.dimension,
        embedding_content_hash=sha256_text("same content"),
        embedding_updated_at=datetime.now(UTC),
    )

    await service._embed_rows([chunk])

    assert model.calls == 0


@pytest.mark.asyncio
async def test_embedding_indexing_refreshes_changed_content() -> None:
    model = FakeEmbeddingModel()
    service = IndexingService(lambda: None, embedding_model=model)
    chunk = Chunk(
        workspace_id=uuid4(),
        revision_id=uuid4(),
        chunk_index=0,
        content="new content",
        token_count=2,
        section_path=[],
        start_offset=0,
        end_offset=11,
        embedding=[1.0, 1.0, 1.0],
        embedding_model=model.model_identity,
        embedding_dimension=model.dimension,
        embedding_content_hash=sha256_text("old content"),
    )

    await service._embed_rows([chunk])

    assert model.calls == 1
    assert chunk.embedding == [11.0, 1.0, 0.5]
    assert chunk.embedding_content_hash == sha256_text("new content")


def test_cosine_similarity_rejects_incompatible_dimensions() -> None:
    assert cosine_similarity([1.0, 0.0], [1.0]) == 0.0
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0
