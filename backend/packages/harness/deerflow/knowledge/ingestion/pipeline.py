from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from deerflow.knowledge.enums import IndexStatus, JobStatus, ParseStatus
from deerflow.knowledge.ingestion.acquisition import ContentAcquirer
from deerflow.knowledge.ingestion.chunker import CHUNKER_NAME, CHUNKER_VERSION, ParentChildChunker
from deerflow.knowledge.ingestion.fingerprint import sha256_content
from deerflow.knowledge.ingestion.models import IngestionResult, SourceInput
from deerflow.knowledge.ingestion.parser_registry import ParserRegistry
from deerflow.knowledge.ingestion.snapshot_store import SnapshotStore
from deerflow.knowledge.ingestion.source_normalizer import SourceNormalizer
from deerflow.knowledge.models import Chunk, DocumentRevision, IngestionJob, Source, SourceSnapshot
from deerflow.knowledge.unit_of_work import KnowledgeUnitOfWork, SessionFactory

PIPELINE_NAME = "ingestion_pipeline"
PIPELINE_VERSION = "1"


class IngestionPipeline:
    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        normalizer: SourceNormalizer | None = None,
        acquirer: ContentAcquirer | None = None,
        parser_registry: ParserRegistry | None = None,
        chunker: ParentChildChunker | None = None,
        snapshot_store: SnapshotStore | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._normalizer = normalizer or SourceNormalizer()
        self._acquirer = acquirer or ContentAcquirer()
        self._parser_registry = parser_registry or ParserRegistry()
        self._chunker = chunker or ParentChildChunker()
        self._snapshot_store = snapshot_store

    async def ingest(self, *, workspace_id: UUID, source_input: SourceInput) -> IngestionResult:
        job_id = await self._create_job(workspace_id, source_input)
        written_snapshot_uri: str | None = None
        try:
            normalized = self._normalizer.normalize(workspace_id, source_input)
            acquired = await self._acquirer.acquire(normalized)
            content_hash = sha256_content(acquired.raw_bytes)
            snapshot_store = self._snapshot_store or SnapshotStore(user_id=source_input.user_id)

            async with KnowledgeUnitOfWork(self._session_factory) as uow:
                assert uow.session is not None
                await _lock_source_identity(uow.session, workspace_id, normalized.canonical_uri)

                source = await uow.sources.get_by_canonical_identity(workspace_id, normalized.source_type, normalized.canonical_uri)
                if source is None:
                    source = await uow.sources.add(
                        Source(
                            workspace_id=workspace_id,
                            source_type=normalized.source_type,
                            canonical_uri=normalized.canonical_uri,
                            title=normalized.display_name,
                            metadata_json=normalized.original_metadata,
                        )
                    )
                else:
                    source.title = normalized.display_name or source.title
                    source.metadata_json = {**(source.metadata_json or {}), **normalized.original_metadata}

                duplicate_snapshot = await uow.snapshots.get_by_source_and_hash(workspace_id, source.id, content_hash)
                if duplicate_snapshot is not None:
                    latest = await uow.revisions.get_latest_for_source(workspace_id, source.id)
                    await self._mark_job_succeeded(uow, job_id, source.id, duplicate_snapshot.id, latest.id if latest else None, deduplicated=True, chunk_count=0)
                    await uow.commit()
                    return IngestionResult(job_id, source.id, duplicate_snapshot.id, latest.id if latest else None, JobStatus.SUCCEEDED, True, 0)

                written_snapshot_uri = snapshot_store.write(workspace_id, content_hash, acquired.raw_bytes)
                snapshot = await uow.snapshots.add(
                    SourceSnapshot(
                        workspace_id=workspace_id,
                        source_id=source.id,
                        content_hash=content_hash,
                        storage_path=written_snapshot_uri,
                        captured_at=acquired.captured_at,
                        parser_version=PIPELINE_VERSION,
                        metadata_json={
                            **acquired.source_metadata,
                            "pipeline_name": PIPELINE_NAME,
                            "pipeline_version": PIPELINE_VERSION,
                        },
                    )
                )

                latest = await uow.revisions.get_latest_for_source(workspace_id, source.id)
                revision = await uow.revisions.add(
                    DocumentRevision(
                        workspace_id=workspace_id,
                        source_id=source.id,
                        snapshot_id=snapshot.id,
                        previous_revision_id=latest.id if latest else None,
                        revision_number=(latest.revision_number + 1) if latest else 1,
                        content_hash=content_hash,
                        parse_status=ParseStatus.PENDING,
                        index_status=IndexStatus.PENDING,
                    )
                )

                parsed = self._parser_registry.parse(acquired.raw_bytes, filename=normalized.display_name, media_type=acquired.media_type or normalized.media_type)
                drafts = self._chunker.chunk(parsed)
                chunk_ids = [uuid4() for _ in drafts]
                chunks = [
                    Chunk(
                        id=chunk_ids[index],
                        workspace_id=workspace_id,
                        revision_id=revision.id,
                        parent_chunk_id=chunk_ids[draft.parent_index] if draft.parent_index is not None else None,
                        chunk_index=draft.chunk_index,
                        content=draft.content,
                        token_count=len(draft.content.split()),
                        page_number=draft.page_number,
                        section_path=list(draft.section_path),
                        start_offset=draft.start_offset,
                        end_offset=draft.end_offset,
                    )
                    for index, draft in enumerate(drafts)
                ]
                await uow.chunks.bulk_add(chunks)
                revision.parse_status = ParseStatus.PARSED
                revision.index_status = IndexStatus.INDEXED
                source.latest_snapshot_id = snapshot.id
                snapshot.metadata_json = {
                    **(snapshot.metadata_json or {}),
                    "parser_name": parsed.parser_name,
                    "parser_version": parsed.parser_version,
                    "chunker_name": CHUNKER_NAME,
                    "chunker_version": CHUNKER_VERSION,
                    "warnings": list(parsed.warnings),
                    "title": parsed.title,
                }
                await self._mark_job_succeeded(uow, job_id, source.id, snapshot.id, revision.id, deduplicated=False, chunk_count=len(chunks))
                await uow.commit()
                written_snapshot_uri = None
                return IngestionResult(job_id, source.id, snapshot.id, revision.id, JobStatus.SUCCEEDED, False, len(chunks), parsed.warnings)
        except IntegrityError:
            if written_snapshot_uri is not None:
                (self._snapshot_store or SnapshotStore(user_id=source_input.user_id)).delete(written_snapshot_uri)
            await self._mark_job_failed(job_id, "Concurrent ingestion conflict; retry is safe")
            raise
        except Exception as exc:
            if written_snapshot_uri is not None:
                (self._snapshot_store or SnapshotStore(user_id=source_input.user_id)).delete(written_snapshot_uri)
            await self._mark_job_failed(job_id, str(exc))
            raise

    async def _create_job(self, workspace_id: UUID, source_input: SourceInput) -> UUID:
        job_id = uuid4()
        async with KnowledgeUnitOfWork(self._session_factory) as uow:
            assert uow.session is not None
            uow.session.add(IngestionJob(id=job_id, workspace_id=workspace_id, source_input=asdict(source_input), status=JobStatus.RUNNING))
            await uow.session.flush()
            await uow.commit()
        return job_id

    async def _mark_job_failed(self, job_id: UUID, error: str) -> None:
        async with KnowledgeUnitOfWork(self._session_factory) as uow:
            assert uow.session is not None
            job = await uow.session.get(IngestionJob, job_id)
            if job is not None:
                job.status = JobStatus.FAILED
                job.error = error[:2000]
                job.completed_at = datetime.now(UTC)
            await uow.commit()

    async def _mark_job_succeeded(
        self,
        uow: KnowledgeUnitOfWork,
        job_id: UUID,
        source_id: UUID,
        snapshot_id: UUID,
        revision_id: UUID | None,
        *,
        deduplicated: bool,
        chunk_count: int,
    ) -> None:
        assert uow.session is not None
        job = await uow.session.get(IngestionJob, job_id)
        if job is not None:
            job.status = JobStatus.SUCCEEDED
            job.completed_at = datetime.now(UTC)
            job.error = None
            job.source_id = source_id
            job.snapshot_id = snapshot_id
            job.revision_id = revision_id
            job.source_input = {**(job.source_input or {}), "deduplicated": deduplicated, "chunk_count": chunk_count}


async def _lock_source_identity(session, workspace_id: UUID, canonical_uri: str) -> None:
    bind = session.get_bind()
    if bind.dialect.name == "postgresql":
        await session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"), {"lock_key": f"{workspace_id}:{canonical_uri}"})
