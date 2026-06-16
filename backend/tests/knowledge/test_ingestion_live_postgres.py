from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select

from deerflow.knowledge.config import KnowledgeDatabaseConfig
from deerflow.knowledge.database import KnowledgeDatabase
from deerflow.knowledge.enums import JobStatus
from deerflow.knowledge.ingestion import IngestionPipeline, SourceInput
from deerflow.knowledge.ingestion.fingerprint import sha256_content
from deerflow.knowledge.ingestion.models import AcquiredContent
from deerflow.knowledge.ingestion.snapshot_store import SnapshotStore
from deerflow.knowledge.models import Chunk, DocumentRevision, IngestionJob, Source, SourceSnapshot

pytestmark = pytest.mark.skipif(not os.getenv("KNOWLEDGE_TEST_DATABASE_URL"), reason="KNOWLEDGE_TEST_DATABASE_URL is not set")


class StaticAcquirer:
    def __init__(self, payloads: list[bytes], media_type: str = "text/plain") -> None:
        self.payloads = payloads
        self.media_type = media_type
        self.calls = 0

    async def acquire(self, source):
        payload = self.payloads[min(self.calls, len(self.payloads) - 1)]
        self.calls += 1
        return AcquiredContent(raw_bytes=payload, media_type=self.media_type, source_metadata={"final_url": source.canonical_uri}, captured_at=datetime.now(UTC))


class FailingParserRegistry:
    def parse(self, *args, **kwargs):
        raise RuntimeError("parse boom")


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


def test_ingestion_pipeline_live_postgres_dedup_revision_failure_and_concurrency() -> None:
    url = os.environ["KNOWLEDGE_TEST_DATABASE_URL"]
    cfg = _alembic_config(url)
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "heads")

    async def run() -> None:
        db = await _initialized_db(url)
        workspace_a = uuid4()
        workspace_b = uuid4()
        source_input = SourceInput(kind="url", value="https://example.com/doc?utm_source=x&a=1#frag", display_name="doc.txt")

        pipeline = IngestionPipeline(db.session_factory, acquirer=StaticAcquirer([b"First version paragraph."]))
        first = await pipeline.ingest(workspace_id=workspace_a, source_input=source_input)
        duplicate = await pipeline.ingest(workspace_id=workspace_a, source_input=source_input)

        assert first.status == JobStatus.SUCCEEDED
        assert not first.deduplicated
        assert duplicate.deduplicated
        assert duplicate.snapshot_id == first.snapshot_id
        assert duplicate.revision_id == first.revision_id

        changed_pipeline = IngestionPipeline(db.session_factory, acquirer=StaticAcquirer([b"Second version paragraph with new bytes."]))
        second = await changed_pipeline.ingest(workspace_id=workspace_a, source_input=source_input)
        assert second.revision_id != first.revision_id

        isolated = await IngestionPipeline(db.session_factory, acquirer=StaticAcquirer([b"First version paragraph."])).ingest(workspace_id=workspace_b, source_input=source_input)
        assert isolated.source_id != first.source_id

        concurrent_input = SourceInput(kind="url", value="https://example.com/concurrent", display_name="concurrent.txt")
        concurrent_pipeline = IngestionPipeline(db.session_factory, acquirer=StaticAcquirer([b"Concurrent bytes."]))
        results = await asyncio.gather(
            concurrent_pipeline.ingest(workspace_id=workspace_a, source_input=concurrent_input),
            concurrent_pipeline.ingest(workspace_id=workspace_a, source_input=concurrent_input),
        )
        assert {result.deduplicated for result in results} == {False, True}

        failing = IngestionPipeline(db.session_factory, acquirer=StaticAcquirer([b"bad"]), parser_registry=FailingParserRegistry())
        with pytest.raises(RuntimeError, match="parse boom"):
            await failing.ingest(workspace_id=workspace_a, source_input=SourceInput(kind="url", value="https://example.com/fail", display_name="fail.txt"))

        async with db.session_factory() as session:
            source = await session.scalar(select(Source).where(Source.id == first.source_id))
            snapshot = await session.scalar(select(SourceSnapshot).where(SourceSnapshot.id == first.snapshot_id))
            assert SnapshotStore().read(snapshot.storage_path) == b"First version paragraph."
            revisions = (await session.execute(select(DocumentRevision).where(DocumentRevision.source_id == source.id).order_by(DocumentRevision.revision_number))).scalars().all()
            assert [revision.revision_number for revision in revisions] == [1, 2]
            chunks = (await session.execute(select(Chunk).where(Chunk.revision_id == first.revision_id).order_by(Chunk.chunk_index))).scalars().all()
            assert chunks[0].parent_chunk_id is None
            assert chunks[1].parent_chunk_id == chunks[0].id
            assert chunks[0].section_path == []
            failed_jobs = await session.scalar(select(func.count()).select_from(IngestionJob).where(IngestionJob.status == JobStatus.FAILED))
            assert failed_jobs == 1
            failed_sources = await session.scalar(select(func.count()).select_from(Source).where(Source.canonical_uri == "https://example.com/fail"))
            assert failed_sources == 0
            failed_snapshot_path = SnapshotStore().path_for(workspace_a, sha256_content(b"bad"))
            assert not failed_snapshot_path.exists()

        await db.dispose()

    asyncio.run(run())
    command.downgrade(cfg, "base")
