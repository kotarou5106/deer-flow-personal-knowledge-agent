from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select

from deerflow.knowledge.enums import JobStatus
from deerflow.knowledge.extraction.model_client import LangChainStructuredExtractionModel, StructuredExtractionModel
from deerflow.knowledge.extraction.persistence import ExtractionPersistence
from deerflow.knowledge.extraction.prompts import PROMPT_VERSION
from deerflow.knowledge.extraction.schemas import (
    EXTRACTOR_NAME,
    EXTRACTOR_VERSION,
    ChunkText,
    ExtractionResult,
    ModelExtractionRequest,
    ValidationSeverity,
)
from deerflow.knowledge.extraction.validator import ExtractionValidator
from deerflow.knowledge.models import DocumentRevision, ExtractionRun
from deerflow.knowledge.unit_of_work import KnowledgeUnitOfWork, SessionFactory


class ExtractionService:
    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        model: StructuredExtractionModel | None = None,
        model_name: str | None = None,
        validator: ExtractionValidator | None = None,
        persistence: ExtractionPersistence | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._model = model or LangChainStructuredExtractionModel(model_name=model_name)
        self._validator = validator or ExtractionValidator()
        self._persistence = persistence or ExtractionPersistence()

    async def extract_revision(self, *, workspace_id: UUID, revision_id: UUID) -> ExtractionResult:
        existing = await self._find_completed_result(workspace_id, revision_id)
        if existing is not None:
            return existing

        run_id = await self._create_run(workspace_id, revision_id)
        processed = 0
        entity_count = 0
        claim_count = 0
        relation_count = 0
        rejected_item_count = 0
        warnings: list[str] = []
        errors: list[str] = []

        chunks = await self._load_child_chunks(workspace_id, revision_id)
        for chunk in chunks:
            try:
                output = await self._model.extract(
                    ModelExtractionRequest(
                        workspace_id=workspace_id,
                        revision_id=revision_id,
                        chunk_id=chunk.id,
                        chunk_text=chunk.content,
                        page_number=chunk.page_number,
                        section_path=chunk.section_path,
                    )
                )
                validated = self._validator.validate(output, [chunk], workspace_id)
                rejected_item_count += validated.rejected_item_count
                warnings.extend(output.warnings)
                warnings.extend(issue.message for issue in validated.issues if issue.severity != ValidationSeverity.REJECTED)
                async with KnowledgeUnitOfWork(self._session_factory) as uow:
                    assert uow.session is not None
                    revision = await uow.revisions.get_by_id(workspace_id, revision_id)
                    if revision is None:
                        raise ValueError("Revision does not belong to workspace")
                    db_chunk = await uow.chunks.get_by_id(workspace_id, chunk.id)
                    if db_chunk is None or db_chunk.revision_id != revision_id:
                        raise ValueError("Chunk does not belong to revision")
                    counts = await self._persistence.persist_chunk_output(
                        uow.session,
                        workspace_id=workspace_id,
                        extraction_run_id=run_id,
                        output=validated.output,
                        chunks_by_id={db_chunk.id: db_chunk},
                    )
                    await uow.commit()
                entity_count += counts.entity_count
                claim_count += counts.claim_count
                relation_count += counts.relation_count
                processed += 1
            except Exception as exc:
                rejected_item_count += 1
                errors.append(f"chunk {chunk.id}: {exc}")

        status = JobStatus.SUCCEEDED if not errors else JobStatus.FAILED
        await self._complete_run(
            workspace_id,
            run_id,
            status,
            processed_chunk_count=processed,
            entity_count=entity_count,
            claim_count=claim_count,
            relation_count=relation_count,
            rejected_item_count=rejected_item_count,
            warnings=warnings,
            errors=errors,
        )
        return ExtractionResult(run_id, revision_id, status, processed, entity_count, claim_count, relation_count, rejected_item_count, warnings)

    async def _find_completed_result(self, workspace_id: UUID, revision_id: UUID) -> ExtractionResult | None:
        async with KnowledgeUnitOfWork(self._session_factory) as uow:
            assert uow.session is not None
            runs = (
                await uow.session.execute(
                    select(ExtractionRun).where(
                        ExtractionRun.workspace_id == workspace_id,
                        ExtractionRun.revision_id == revision_id,
                        ExtractionRun.status == JobStatus.SUCCEEDED,
                    )
                )
            ).scalars()
            for run in runs:
                metadata = run.metadata_json or {}
                if metadata.get("extractor_name") == EXTRACTOR_NAME and metadata.get("extractor_version") == EXTRACTOR_VERSION and metadata.get("model_identity") == self._model.model_identity and run.prompt_version == PROMPT_VERSION:
                    return ExtractionResult(
                        extraction_run_id=run.id,
                        revision_id=revision_id,
                        status=run.status,
                        processed_chunk_count=int(metadata.get("processed_chunk_count", 0)),
                        entity_count=int(metadata.get("entity_count", 0)),
                        claim_count=int(metadata.get("claim_count", 0)),
                        relation_count=int(metadata.get("relation_count", 0)),
                        rejected_item_count=int(metadata.get("rejected_item_count", 0)),
                        warnings=list(metadata.get("warnings", [])),
                    )
        return None

    async def _create_run(self, workspace_id: UUID, revision_id: UUID) -> UUID:
        run_id = uuid4()
        async with KnowledgeUnitOfWork(self._session_factory) as uow:
            assert uow.session is not None
            revision = await uow.session.get(DocumentRevision, revision_id)
            if revision is None or revision.workspace_id != workspace_id:
                raise ValueError("Revision does not belong to workspace")
            uow.session.add(
                ExtractionRun(
                    id=run_id,
                    workspace_id=workspace_id,
                    revision_id=revision_id,
                    model_name=self._model.model_identity,
                    prompt_version=PROMPT_VERSION,
                    status=JobStatus.RUNNING,
                    metadata_json={
                        "extractor_name": EXTRACTOR_NAME,
                        "extractor_version": EXTRACTOR_VERSION,
                        "model_identity": self._model.model_identity,
                    },
                )
            )
            await uow.session.flush()
            await uow.commit()
        return run_id

    async def _load_child_chunks(self, workspace_id: UUID, revision_id: UUID) -> list[ChunkText]:
        async with KnowledgeUnitOfWork(self._session_factory) as uow:
            chunks = await uow.chunks.list_for_revision(workspace_id, revision_id)
            child_chunks = [chunk for chunk in chunks if chunk.parent_chunk_id is not None]
            selected = child_chunks or chunks
            return [
                ChunkText(
                    id=chunk.id,
                    revision_id=chunk.revision_id,
                    workspace_id=chunk.workspace_id,
                    content=chunk.content,
                    page_number=chunk.page_number,
                    section_path=[str(part) for part in (chunk.section_path or [])],
                )
                for chunk in selected
            ]

    async def _complete_run(
        self,
        workspace_id: UUID,
        run_id: UUID,
        status: JobStatus,
        *,
        processed_chunk_count: int,
        entity_count: int,
        claim_count: int,
        relation_count: int,
        rejected_item_count: int,
        warnings: list[str],
        errors: list[str],
    ) -> None:
        async with KnowledgeUnitOfWork(self._session_factory) as uow:
            assert uow.session is not None
            run = await uow.extraction_runs.get_by_id(workspace_id, run_id)
            if run is not None:
                run.status = status
                run.completed_at = datetime.now(UTC)
                run.error = "\n".join(errors)[:2000] if errors else None
                run.metadata_json = {
                    **(run.metadata_json or {}),
                    "processed_chunk_count": processed_chunk_count,
                    "entity_count": entity_count,
                    "claim_count": claim_count,
                    "relation_count": relation_count,
                    "rejected_item_count": rejected_item_count,
                    "warnings": warnings,
                }
            await uow.commit()
