from __future__ import annotations

import asyncio
import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config

from deerflow.knowledge.config import KnowledgeDatabaseConfig
from deerflow.knowledge.database import KnowledgeDatabase
from deerflow.knowledge.enums import ClaimStance, ClaimStatus, IndexStatus, JobStatus, ParseStatus
from deerflow.knowledge.models import (
    Chunk,
    Claim,
    ClaimEvidenceLink,
    DocumentRevision,
    Entity,
    EntityAlias,
    EvidenceSpan,
    IndexingRun,
    Relation,
    Source,
    SourceSnapshot,
)
from deerflow.knowledge.retrieval import IndexingService, RetrievalService
from deerflow.knowledge.retrieval.schemas import CandidateType

pytestmark = pytest.mark.skipif(not os.getenv("KNOWLEDGE_TEST_DATABASE_URL"), reason="KNOWLEDGE_TEST_DATABASE_URL is not set")


class FakeEmbeddingModel:
    model_identity = "fake-retrieval-embedding"
    dimension = 3

    def __init__(self) -> None:
        self.calls = 0

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        return [_vector_for(text) for text in texts]


def _vector_for(text: str) -> list[float]:
    lowered = text.casefold()
    return [
        1.0 if "acme" in lowered else 0.0,
        1.0 if "beta" in lowered or "收购" in lowered or "acquired" in lowered else 0.0,
        1.0 if "2024" in lowered else 0.0,
    ]


def _alembic_config(url: str) -> Config:
    script = Path.cwd() / "packages/harness/deerflow/persistence/migrations"
    cfg = Config(str(script / "alembic.ini"))
    cfg.set_main_option("script_location", str(script))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


async def _initialized_db(url: str) -> KnowledgeDatabase:
    db = KnowledgeDatabase(KnowledgeDatabaseConfig(database_url=url))
    await db.initialize()
    return db


async def _seed(db: KnowledgeDatabase, workspace_id, content: str):
    async with db.session_factory() as session:
        source = Source(workspace_id=workspace_id, source_type="url", canonical_uri=f"https://example.com/{uuid4()}", title="Acme acquisition memo")
        session.add(source)
        await session.flush()
        snapshot = SourceSnapshot(workspace_id=workspace_id, source_id=source.id, content_hash=str(uuid4()), storage_path="memory://snapshot")
        session.add(snapshot)
        await session.flush()
        revision = DocumentRevision(
            workspace_id=workspace_id,
            source_id=source.id,
            snapshot_id=snapshot.id,
            revision_number=1,
            content_hash=snapshot.content_hash,
            parse_status=ParseStatus.PARSED,
            index_status=IndexStatus.INDEXED,
        )
        session.add(revision)
        await session.flush()
        parent = Chunk(
            workspace_id=workspace_id,
            revision_id=revision.id,
            chunk_index=0,
            content="Parent section: acquisition context and timeline.",
            token_count=6,
            section_path=["M&A"],
            start_offset=0,
            end_offset=49,
        )
        session.add(parent)
        await session.flush()
        child = Chunk(
            workspace_id=workspace_id,
            revision_id=revision.id,
            parent_chunk_id=parent.id,
            chunk_index=1,
            content=content,
            token_count=len(content.split()),
            page_number=1,
            section_path=["M&A", "Deal"],
            start_offset=0,
            end_offset=len(content),
        )
        session.add(child)
        await session.flush()
        acme = Entity(workspace_id=workspace_id, canonical_name="Acme", entity_type="organization")
        beta = Entity(workspace_id=workspace_id, canonical_name="Beta", entity_type="organization")
        session.add_all([acme, beta])
        await session.flush()
        session.add(EntityAlias(workspace_id=workspace_id, entity_id=acme.id, alias="ACME"))
        evidence = EvidenceSpan(workspace_id=workspace_id, chunk_id=child.id, start_offset=0, end_offset=len(content), quoted_text=content, page_number=1)
        session.add(evidence)
        await session.flush()
        claim = Claim(
            workspace_id=workspace_id,
            normalized_subject="Acme",
            predicate="acquired",
            normalized_object="Beta",
            claim_text=content,
            stance=ClaimStance.SUPPORTS,
            confidence=0.9,
            status=ClaimStatus.ACTIVE,
            metadata_json={"subject_entity_id": str(acme.id), "object_entity_id": str(beta.id)},
        )
        session.add(claim)
        await session.flush()
        session.add(ClaimEvidenceLink(workspace_id=workspace_id, claim_id=claim.id, evidence_span_id=evidence.id))
        session.add(
            Relation(
                workspace_id=workspace_id,
                source_entity_id=acme.id,
                relation_type="acquired",
                target_entity_id=beta.id,
                evidence_span_id=evidence.id,
                confidence=0.9,
            )
        )
        await session.commit()
        return revision.id, source.id, child.id, parent.id, claim.id


def test_hybrid_retrieval_live_postgres_indexing_retrieval_and_context_pack() -> None:
    url = os.environ["KNOWLEDGE_TEST_DATABASE_URL"]
    cfg = _alembic_config(url)
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "heads")

    async def run() -> None:
        db = await _initialized_db(url)
        workspace_a = uuid4()
        workspace_b = uuid4()
        content = "Acme 收购 Beta in 2024."
        revision_id, source_id, child_id, parent_id, claim_id = await _seed(db, workspace_a, content)
        other_revision_id, *_ = await _seed(db, workspace_b, "Other workspace Acme 收购 Beta in 2024.")
        embedding_model = FakeEmbeddingModel()

        run_id = await IndexingService(db.session_factory, embedding_model=embedding_model).index_revision(workspace_id=workspace_a, revision_id=revision_id)
        await IndexingService(db.session_factory, embedding_model=embedding_model).index_revision(workspace_id=workspace_a, revision_id=revision_id)
        await IndexingService(db.session_factory, embedding_model=embedding_model).index_revision(workspace_id=workspace_b, revision_id=other_revision_id)

        pack = await RetrievalService(db.session_factory, embedding_model=embedding_model).retrieve(
            workspace_id=workspace_a,
            query="Acme 收购",
            filters={"source_ids": [source_id], "top_k": 10, "graph_depth": 2},
            context_budget=2000,
        )

        assert any(candidate.candidate_id == child_id for candidate in pack.retrieved_chunks)
        assert any(candidate.candidate_id == parent_id and candidate.is_context_expansion for candidate in pack.retrieved_chunks)
        assert any(candidate.candidate_id == claim_id for candidate in pack.claims)
        assert any(candidate.candidate_type == CandidateType.RELATION for candidate in pack.relations)
        assert any(candidate.candidate_type == CandidateType.EVIDENCE for candidate in pack.evidence_spans)
        assert str(source_id) in {source["source_id"] for source in pack.sources}
        assert all(candidate.workspace_id == workspace_a for candidate in [*pack.retrieved_chunks, *pack.claims, *pack.relations, *pack.evidence_spans])
        assert any("lexical" in scores or "vector_chunk" in scores or "graph" in scores for scores in pack.channel_scores.values())

        async with db.session_factory() as session:
            run = await session.get(IndexingRun, run_id)
            assert run.status == JobStatus.SUCCEEDED
            chunk = await session.get(Chunk, child_id)
            assert chunk.content_tsv is not None
            assert chunk.embedding_model == embedding_model.model_identity
            claim = await session.get(Claim, claim_id)
            assert claim.embedding_model == embedding_model.model_identity

        await db.dispose()

    try:
        asyncio.run(run())
    finally:
        command.downgrade(cfg, "base")
