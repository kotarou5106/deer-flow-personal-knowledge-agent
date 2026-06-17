from __future__ import annotations

from uuid import uuid4

import pytest

from deerflow.knowledge.enums import ClaimStatus, JobStatus
from deerflow.knowledge.models import Chunk, Claim, DocumentRevision
from deerflow.knowledge.retrieval.vector import VectorRetriever
from deerflow.knowledge.updates import build_incremental_processing_plan, diff_revisions, render_markdown_report
from deerflow.knowledge.updates.schemas import KnowledgeUpdateReport, RevisionDiffSummary


def _revision(workspace_id, source_id, *, number: int) -> DocumentRevision:
    return DocumentRevision(
        id=uuid4(),
        workspace_id=workspace_id,
        source_id=source_id,
        snapshot_id=uuid4(),
        revision_number=number,
        content_hash=str(uuid4()),
    )


def _chunk(revision_id, workspace_id, index: int, content: str, *, section: list[str] | None = None, page: int | None = None) -> Chunk:
    return Chunk(
        id=uuid4(),
        workspace_id=workspace_id,
        revision_id=revision_id,
        parent_chunk_id=uuid4(),
        chunk_index=index,
        content=content,
        token_count=len(content.split()),
        page_number=page,
        section_path=section or [],
        start_offset=index * 100,
        end_offset=index * 100 + len(content),
    )


def test_revision_diff_classifies_unchanged_added_removed_modified_and_moved() -> None:
    workspace_id = uuid4()
    source_id = uuid4()
    old_revision = _revision(workspace_id, source_id, number=1)
    new_revision = _revision(workspace_id, source_id, number=2)
    old_same = _chunk(old_revision.id, workspace_id, 1, "same", section=["A"], page=1)
    old_removed = _chunk(old_revision.id, workspace_id, 2, "removed", section=["B"], page=2)
    old_modified = _chunk(old_revision.id, workspace_id, 3, "old value", section=["C"], page=3)
    old_moved = _chunk(old_revision.id, workspace_id, 4, "moved text", section=["D"], page=4)
    new_same = _chunk(new_revision.id, workspace_id, 1, "same", section=["A"], page=1)
    new_modified = _chunk(new_revision.id, workspace_id, 3, "new value", section=["C"], page=3)
    new_moved = _chunk(new_revision.id, workspace_id, 8, "moved text", section=["Z"], page=9)
    new_added = _chunk(new_revision.id, workspace_id, 9, "added", section=["N"], page=10)

    diff = diff_revisions(old_revision, new_revision, [old_same, old_removed, old_modified, old_moved], [new_same, new_modified, new_moved, new_added])

    assert diff.summary == RevisionDiffSummary(unchanged=1, added=1, removed=1, modified=1, moved=1)
    assert diff.unchanged_pairs[0].old_chunk_id == old_same.id
    assert diff.modified_pairs[0].old_chunk_id == old_modified.id
    assert diff.moved_pairs[0].old_chunk_id == old_moved.id
    assert diff.added_chunk_ids == (new_added.id,)
    assert diff.removed_chunk_ids == (old_removed.id,)

    plan = build_incremental_processing_plan(diff)
    assert plan.reprocess_chunk_ids == tuple(sorted([new_added.id, new_modified.id], key=str))
    assert plan.reused_chunk_ids == tuple(sorted([new_same.id, new_moved.id], key=str))


def test_revision_diff_rejects_cross_workspace_and_cross_source() -> None:
    source_id = uuid4()
    old_revision = _revision(uuid4(), source_id, number=1)
    new_revision = _revision(uuid4(), source_id, number=2)
    with pytest.raises(ValueError, match="workspaces"):
        diff_revisions(old_revision, new_revision, [], [])

    workspace_id = uuid4()
    old_revision = _revision(workspace_id, uuid4(), number=1)
    new_revision = _revision(workspace_id, uuid4(), number=2)
    with pytest.raises(ValueError, match="different sources"):
        diff_revisions(old_revision, new_revision, [], [])


def test_markdown_report_renders_update_summary() -> None:
    report = KnowledgeUpdateReport(
        run_id=uuid4(),
        source_id=uuid4(),
        old_revision_id=uuid4(),
        new_revision_id=uuid4(),
        status=JobStatus.SUCCEEDED,
        diff_summary=RevisionDiffSummary(unchanged=1, added=2, removed=3, modified=4, moved=5),
        reprocessed_chunks=(uuid4(),),
        reused_chunks=(uuid4(), uuid4()),
    )

    rendered = render_markdown_report(report)

    assert "Knowledge Update Report" in rendered
    assert "Modified: 4" in rendered
    assert "Reused chunks: 2" in rendered


@pytest.mark.asyncio
async def test_vector_claim_retrieval_adds_active_claim_filter() -> None:
    class FakeEmbedding:
        model_identity = "fake"
        dimension = 2

        async def embed_texts(self, texts: list[str]) -> list[list[float]]:
            return [[1.0, 0.0] for _ in texts]

    workspace_id = uuid4()
    active = Claim(
        id=uuid4(),
        workspace_id=workspace_id,
        claim_text="active",
        status=ClaimStatus.ACTIVE,
        embedding=[1.0, 0.0],
        embedding_model="fake",
        embedding_dimension=2,
    )
    superseded = Claim(
        id=uuid4(),
        workspace_id=workspace_id,
        claim_text="old",
        status=ClaimStatus.SUPERSEDED,
        embedding=[1.0, 0.0],
        embedding_model="fake",
        embedding_dimension=2,
    )
    seen_where = []

    class FakeResult:
        def scalars(self):
            return [active, superseded]

    class FakeSession:
        async def execute(self, stmt):
            seen_where.append(str(stmt))
            return FakeResult()

    retriever = VectorRetriever(FakeEmbedding())
    rows = await retriever._retrieve_claims(FakeSession(), workspace_id, type("Query", (), {"top_k": 5})(), [1.0, 0.0])

    assert rows
    assert "knowledge_claims.status" in seen_where[0]
