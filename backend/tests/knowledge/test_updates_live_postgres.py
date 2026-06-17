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
from deerflow.knowledge.enums import ArtifactStalenessStatus, ClaimStatus, IndexStatus, JobStatus, ParseStatus
from deerflow.knowledge.models import (
    Artifact,
    ArtifactEvidenceLink,
    Chunk,
    Claim,
    ClaimEvidenceLink,
    ConflictGroup,
    DocumentRevision,
    EvidenceSpan,
    KnowledgeUpdateRun,
    Source,
    SourceSnapshot,
)
from deerflow.knowledge.updates import KnowledgeUpdateService

pytestmark = pytest.mark.skipif(not os.getenv("KNOWLEDGE_UPDATE_TEST_DATABASE_URL"), reason="KNOWLEDGE_UPDATE_TEST_DATABASE_URL is not set")


class RecordingProcessor:
    def __init__(self) -> None:
        self.calls: list = []

    async def process_chunk(self, *, workspace_id, revision_id, chunk_id) -> None:
        self.calls.append((workspace_id, revision_id, chunk_id))


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


async def _seed_revision_pair(db: KnowledgeDatabase, workspace_id):
    async with db.session_factory() as session:
        source = Source(workspace_id=workspace_id, source_type="file", canonical_uri=f"user-file://{uuid4()}", title="source")
        other_source = Source(workspace_id=workspace_id, source_type="url", canonical_uri=f"https://example.com/{uuid4()}", title="other")
        isolated_source = Source(workspace_id=uuid4(), source_type="file", canonical_uri=f"user-file://{uuid4()}", title="isolated")
        session.add_all([source, other_source, isolated_source])
        await session.flush()
        old_snapshot = SourceSnapshot(workspace_id=workspace_id, source_id=source.id, content_hash=f"old-{uuid4()}", storage_path="memory://old")
        new_snapshot = SourceSnapshot(workspace_id=workspace_id, source_id=source.id, content_hash=f"new-{uuid4()}", storage_path="memory://new")
        other_snapshot = SourceSnapshot(workspace_id=workspace_id, source_id=other_source.id, content_hash=f"other-{uuid4()}", storage_path="memory://other")
        session.add_all([old_snapshot, new_snapshot, other_snapshot])
        await session.flush()
        old_revision = DocumentRevision(
            workspace_id=workspace_id,
            source_id=source.id,
            snapshot_id=old_snapshot.id,
            revision_number=1,
            content_hash=old_snapshot.content_hash,
            parse_status=ParseStatus.PARSED,
            index_status=IndexStatus.INDEXED,
        )
        new_revision = DocumentRevision(
            workspace_id=workspace_id,
            source_id=source.id,
            snapshot_id=new_snapshot.id,
            previous_revision_id=old_revision.id,
            revision_number=2,
            content_hash=new_snapshot.content_hash,
            parse_status=ParseStatus.PARSED,
            index_status=IndexStatus.INDEXED,
        )
        other_revision = DocumentRevision(
            workspace_id=workspace_id,
            source_id=other_source.id,
            snapshot_id=other_snapshot.id,
            revision_number=1,
            content_hash=other_snapshot.content_hash,
            parse_status=ParseStatus.PARSED,
            index_status=IndexStatus.INDEXED,
        )
        session.add_all([old_revision, new_revision, other_revision])
        await session.flush()

        old_same = _chunk(workspace_id, old_revision.id, 1, "same content", section=["A"], page=1)
        old_removed = _chunk(workspace_id, old_revision.id, 2, "removed claim", section=["B"], page=2)
        old_modified = _chunk(workspace_id, old_revision.id, 3, "old value", section=["C"], page=3)
        old_moved = _chunk(workspace_id, old_revision.id, 4, "moved content", section=["D"], page=4)
        new_same = _chunk(workspace_id, new_revision.id, 1, "same content", section=["A"], page=1)
        new_modified = _chunk(workspace_id, new_revision.id, 3, "new value", section=["C"], page=3)
        new_moved = _chunk(workspace_id, new_revision.id, 8, "moved content", section=["Z"], page=9)
        new_added = _chunk(workspace_id, new_revision.id, 9, "added conflict", section=["N"], page=10)
        other_chunk = _chunk(workspace_id, other_revision.id, 1, "other conflict", section=["O"], page=1)
        session.add_all([old_same, old_removed, old_modified, old_moved, new_same, new_modified, new_moved, new_added, other_chunk])
        await session.flush()

        old_removed_claim = await _claim_with_evidence(session, workspace_id, old_removed, "Acme had legacy policy.", "acme", "policy", "legacy")
        old_modified_claim = await _claim_with_evidence(session, workspace_id, old_modified, "Acme revenue is 10.", "acme", "revenue", "10")
        new_modified_claim = await _claim_with_evidence(session, workspace_id, new_modified, "Acme revenue is 10 updated.", "acme", "revenue", "10")
        new_added_claim = await _claim_with_evidence(session, workspace_id, new_added, "Acme revenue is 20.", "acme", "revenue", "20")
        other_claim = await _claim_with_evidence(session, workspace_id, other_chunk, "Acme revenue is 30.", "acme", "revenue", "30")
        isolated_claim = Claim(
            workspace_id=isolated_source.workspace_id,
            claim_text="Workspace B should not change.",
            normalized_subject="acme",
            predicate="revenue",
            normalized_object="10",
            status=ClaimStatus.ACTIVE,
        )
        session.add(isolated_claim)
        artifact = Artifact(workspace_id=workspace_id, artifact_type="markdown", title="answer", storage_path="memory://artifact")
        session.add(artifact)
        await session.flush()
        session.add(
            ArtifactEvidenceLink(
                workspace_id=workspace_id,
                artifact_id=artifact.id,
                claim_id=old_modified_claim.id,
                revision_id=old_revision.id,
                usage_type="citation",
            )
        )
        await session.commit()
        return {
            "source_id": source.id,
            "old_revision_id": old_revision.id,
            "new_revision_id": new_revision.id,
            "new_modified_id": new_modified.id,
            "new_added_id": new_added.id,
            "new_same_id": new_same.id,
            "new_moved_id": new_moved.id,
            "old_removed_claim_id": old_removed_claim.id,
            "old_modified_claim_id": old_modified_claim.id,
            "new_modified_claim_id": new_modified_claim.id,
            "new_added_claim_id": new_added_claim.id,
            "other_claim_id": other_claim.id,
            "isolated_claim_id": isolated_claim.id,
            "artifact_id": artifact.id,
        }


def _chunk(workspace_id, revision_id, index: int, content: str, *, section: list[str], page: int) -> Chunk:
    return Chunk(
        workspace_id=workspace_id,
        revision_id=revision_id,
        parent_chunk_id=None,
        chunk_index=index,
        content=content,
        token_count=len(content.split()),
        page_number=page,
        section_path=section,
        start_offset=index * 100,
        end_offset=index * 100 + len(content),
    )


async def _claim_with_evidence(session, workspace_id, chunk: Chunk, text: str, subject: str, predicate: str, obj: str) -> Claim:
    evidence = EvidenceSpan(workspace_id=workspace_id, chunk_id=chunk.id, start_offset=0, end_offset=len(chunk.content), quoted_text=chunk.content, page_number=chunk.page_number)
    claim = Claim(
        workspace_id=workspace_id,
        claim_text=text,
        normalized_subject=subject,
        predicate=predicate,
        normalized_object=obj,
        status=ClaimStatus.ACTIVE,
    )
    session.add_all([evidence, claim])
    await session.flush()
    session.add(ClaimEvidenceLink(workspace_id=workspace_id, claim_id=claim.id, evidence_span_id=evidence.id))
    await session.flush()
    return claim


def test_knowledge_update_service_live_postgres_revision_diff_lifecycle_conflicts_and_retry() -> None:
    url = os.environ["KNOWLEDGE_UPDATE_TEST_DATABASE_URL"]
    cfg = _alembic_config(url)
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "heads")

    async def run() -> None:
        db = await _initialized_db(url)
        workspace_id = uuid4()
        seeded = await _seed_revision_pair(db, workspace_id)
        processor = RecordingProcessor()
        service = KnowledgeUpdateService(db.session_factory, extraction_processor=processor, indexing_processor=processor)

        first = await service.process_revision_update(workspace_id=workspace_id, old_revision_id=seeded["old_revision_id"], new_revision_id=seeded["new_revision_id"])
        second = await service.process_revision_update(workspace_id=workspace_id, old_revision_id=seeded["old_revision_id"], new_revision_id=seeded["new_revision_id"])

        assert first.status == JobStatus.SUCCEEDED
        assert second.run_id == first.run_id
        assert first.diff_summary.unchanged == 1
        assert first.diff_summary.added == 1
        assert first.diff_summary.modified == 1
        assert first.diff_summary.moved == 1
        assert tuple(sorted(first.reprocessed_chunks, key=str)) == tuple(sorted([seeded["new_modified_id"], seeded["new_added_id"]], key=str))
        assert tuple(sorted(first.reused_chunks, key=str)) == tuple(sorted([seeded["new_same_id"], seeded["new_moved_id"]], key=str))
        assert len(processor.calls) == 4

        async with db.session_factory() as session:
            old_modified = await session.get(Claim, seeded["old_modified_claim_id"])
            old_removed = await session.get(Claim, seeded["old_removed_claim_id"])
            new_added = await session.get(Claim, seeded["new_added_claim_id"])
            isolated = await session.get(Claim, seeded["isolated_claim_id"])
            artifact = await session.get(Artifact, seeded["artifact_id"])
            assert old_modified.status == ClaimStatus.SUPERSEDED
            assert old_modified.metadata_json["lifecycle_status"] == "superseded"
            assert old_removed.status == ClaimStatus.INVALIDATED
            assert new_added.metadata_json["lifecycle_status"] == "pending_conflict_review"
            assert isolated.status == ClaimStatus.ACTIVE
            assert artifact.staleness_status == ArtifactStalenessStatus.STALE
            assert artifact.metadata_json["requires_review"] is True
            assert await session.scalar(select(func.count()).select_from(KnowledgeUpdateRun).where(KnowledgeUpdateRun.workspace_id == workspace_id)) == 1
            assert await session.scalar(select(func.count()).select_from(ConflictGroup).where(ConflictGroup.workspace_id == workspace_id)) >= 1
            conflict = await session.scalar(select(ConflictGroup).where(ConflictGroup.workspace_id == workspace_id).limit(1))
            assert conflict.metadata_json["classification"] in {"source_disagreement", "temporal_update", "possible_conflict"}

        await db.dispose()

    try:
        asyncio.run(run())
    finally:
        command.downgrade(cfg, "base")
