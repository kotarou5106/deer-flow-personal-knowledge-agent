from __future__ import annotations

import asyncio
import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select

from deerflow.knowledge.config import KnowledgeDatabaseConfig
from deerflow.knowledge.database import KnowledgeDatabase
from deerflow.knowledge.enums import ClaimStance, ClaimStatus, IndexStatus, JobStatus, ParseStatus
from deerflow.knowledge.extraction import ExtractionService
from deerflow.knowledge.extraction.schemas import (
    ExtractedClaim,
    ExtractedEntity,
    ExtractedEvidenceSpan,
    ExtractedRelation,
    ModelExtractionRequest,
    StructuredExtractionOutput,
)
from deerflow.knowledge.models import (
    Chunk,
    Claim,
    ClaimEvidenceLink,
    DocumentRevision,
    Entity,
    EvidenceSpan,
    ExtractionRun,
    Relation,
    Source,
    SourceSnapshot,
)

pytestmark = pytest.mark.skipif(not os.getenv("KNOWLEDGE_TEST_DATABASE_URL"), reason="KNOWLEDGE_TEST_DATABASE_URL is not set")


class FakeStructuredModel:
    model_identity = "fake-structured-model"

    def __init__(self, *, fail_on_text: str | None = None) -> None:
        self.fail_on_text = fail_on_text
        self.calls = 0

    async def extract(self, request: ModelExtractionRequest) -> StructuredExtractionOutput:
        self.calls += 1
        if self.fail_on_text and self.fail_on_text in request.chunk_text:
            raise RuntimeError("model chunk failure")
        return _output_for(request.chunk_id, request.chunk_text)


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


def _output_for(chunk_id, text: str) -> StructuredExtractionOutput:
    quote = "Acme acquired Beta in 2024."
    start = text.index(quote)
    end = start + len(quote)
    evidence = ExtractedEvidenceSpan(chunk_id=chunk_id, start_offset=start, end_offset=end, quoted_text=quote)
    return StructuredExtractionOutput(
        entities=[
            ExtractedEntity(local_id="acme", canonical_name="Acme", entity_type="organization", aliases=["ACME"], confidence=0.95),
            ExtractedEntity(local_id="beta", canonical_name="Beta", entity_type="organization", aliases=[], confidence=0.9),
        ],
        claims=[
            ExtractedClaim(
                local_id="claim-1",
                subject_entity_local_id="acme",
                predicate="acquired",
                object_entity_local_id="beta",
                claim_text=quote,
                stance=ClaimStance.SUPPORTS,
                confidence=0.87,
                evidence_spans=[evidence],
            )
        ],
        relations=[
            ExtractedRelation(
                source_entity_local_id="acme",
                relation_type="acquired",
                target_entity_local_id="beta",
                confidence=0.86,
                evidence_spans=[evidence],
            )
        ],
    )


async def _seed_revision(db: KnowledgeDatabase, workspace_id, *, child_texts: list[str]):
    async with db.session_factory() as session:
        source = Source(workspace_id=workspace_id, source_type="url", canonical_uri=f"https://example.com/{uuid4()}", title="source")
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
            content="Parent context",
            token_count=2,
            section_path=[],
            start_offset=0,
            end_offset=14,
        )
        session.add(parent)
        await session.flush()
        for index, text in enumerate(child_texts, start=1):
            session.add(
                Chunk(
                    workspace_id=workspace_id,
                    revision_id=revision.id,
                    parent_chunk_id=parent.id,
                    chunk_index=index,
                    content=text,
                    token_count=len(text.split()),
                    page_number=index,
                    section_path=["Section"],
                    start_offset=0,
                    end_offset=len(text),
                )
            )
        await session.commit()
        return revision.id


def test_extraction_service_live_postgres_persistence_idempotency_and_partial_failure() -> None:
    url = os.environ["KNOWLEDGE_TEST_DATABASE_URL"]
    cfg = _alembic_config(url)
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "heads")

    async def run() -> None:
        db = await _initialized_db(url)
        workspace_a = uuid4()
        workspace_b = uuid4()

        revision_a = await _seed_revision(db, workspace_a, child_texts=["Intro. Acme acquired Beta in 2024."])
        model = FakeStructuredModel()
        service = ExtractionService(db.session_factory, model=model)
        first = await service.extract_revision(workspace_id=workspace_a, revision_id=revision_a)
        second = await service.extract_revision(workspace_id=workspace_a, revision_id=revision_a)

        assert first.status == JobStatus.SUCCEEDED
        assert first.processed_chunk_count == 1
        assert first.entity_count == 2
        assert first.claim_count == 1
        assert first.relation_count == 1
        assert second.extraction_run_id == first.extraction_run_id
        assert model.calls == 1

        revision_b = await _seed_revision(db, workspace_b, child_texts=["Acme acquired Beta in 2024."])
        isolated = await ExtractionService(db.session_factory, model=FakeStructuredModel()).extract_revision(workspace_id=workspace_b, revision_id=revision_b)
        assert isolated.status == JobStatus.SUCCEEDED

        partial_revision = await _seed_revision(
            db,
            workspace_a,
            child_texts=["Acme acquired Beta in 2024.", "Acme acquired Beta in 2024. fail this chunk"],
        )
        partial = await ExtractionService(db.session_factory, model=FakeStructuredModel(fail_on_text="fail this chunk")).extract_revision(
            workspace_id=workspace_a,
            revision_id=partial_revision,
        )
        assert partial.status == JobStatus.FAILED
        assert partial.processed_chunk_count == 1
        assert partial.rejected_item_count == 1

        async with db.session_factory() as session:
            entity_count_a = await session.scalar(select(func.count()).select_from(Entity).where(Entity.workspace_id == workspace_a))
            entity_count_b = await session.scalar(select(func.count()).select_from(Entity).where(Entity.workspace_id == workspace_b))
            assert entity_count_a == 2
            assert entity_count_b == 2
            assert await session.scalar(select(func.count()).select_from(Claim).where(Claim.workspace_id == workspace_a)) == 2
            assert await session.scalar(select(func.count()).select_from(Claim).where(Claim.workspace_id == workspace_b)) == 1
            assert await session.scalar(select(func.count()).select_from(EvidenceSpan).where(EvidenceSpan.workspace_id == workspace_a)) == 2
            assert await session.scalar(select(func.count()).select_from(Relation).where(Relation.workspace_id == workspace_a)) == 2
            assert await session.scalar(select(func.count()).select_from(ClaimEvidenceLink).where(ClaimEvidenceLink.workspace_id == workspace_a)) == 2
            active_claim = await session.scalar(select(Claim).where(Claim.workspace_id == workspace_a, Claim.status == ClaimStatus.ACTIVE).limit(1))
            assert active_claim is not None
            run = await session.scalar(select(ExtractionRun).where(ExtractionRun.id == partial.extraction_run_id))
            assert run.status == JobStatus.FAILED
            assert "model chunk failure" in run.error
            assert run.metadata_json["extractor_version"] == "1"

        await db.dispose()

    try:
        asyncio.run(run())
    finally:
        command.downgrade(cfg, "base")
