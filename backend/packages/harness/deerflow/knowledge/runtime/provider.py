from __future__ import annotations

import asyncio
import hashlib
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Protocol
from uuid import UUID, uuid4

from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from deerflow.knowledge.analysis import AnalysisService
from deerflow.knowledge.analysis.model_client import DeterministicAnalysisModel
from deerflow.knowledge.config import KnowledgeDatabaseConfig
from deerflow.knowledge.database import KnowledgeDatabase
from deerflow.knowledge.enums import ApprovalStatus, ClaimStatus, JobStatus, RiskLevel
from deerflow.knowledge.extraction import ExtractionService
from deerflow.knowledge.extraction.model_client import DeterministicStructuredExtractionModel
from deerflow.knowledge.extraction.persistence import ExtractionPersistence
from deerflow.knowledge.extraction.schemas import ChunkText, ModelExtractionRequest
from deerflow.knowledge.extraction.validator import ExtractionValidator
from deerflow.knowledge.ingestion.models import SourceInput
from deerflow.knowledge.ingestion.pipeline import IngestionPipeline
from deerflow.knowledge.models import ApprovalRequest, Chunk, Claim, ConflictGroup, ExtractionRun
from deerflow.knowledge.retrieval.service import RetrievalService
from deerflow.knowledge.runtime.context import TrustedKnowledgeContext
from deerflow.knowledge.unit_of_work import KnowledgeUnitOfWork, SessionFactory
from deerflow.knowledge.updates import KnowledgeUpdateService, diff_revisions, render_markdown_report
from deerflow.knowledge.updates.impact_analyzer import build_incremental_processing_plan
from deerflow.knowledge.updates.schemas import (
    ChunkChangeType,
    IncrementalProcessingPlan,
    RevisionDiff,
)


class KnowledgeServiceUnavailableError(RuntimeError):
    pass


class KnowledgeServiceProvider(Protocol):
    async def initialize(self) -> None: ...

    async def dispose(self) -> None: ...

    async def ingest(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]: ...

    async def ingestion_status(self, context: TrustedKnowledgeContext, job_id: str) -> dict[str, Any]: ...

    async def overview(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]: ...

    async def search(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]: ...

    async def analyze(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]: ...

    async def get_source(self, context: TrustedKnowledgeContext, source_id: str) -> dict[str, Any]: ...

    async def list_sources(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]: ...

    async def get_source_detail(self, context: TrustedKnowledgeContext, source_id: str) -> dict[str, Any]: ...

    async def list_source_revisions(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]: ...

    async def get_revision(self, context: TrustedKnowledgeContext, revision_id: str) -> dict[str, Any]: ...

    async def get_claims(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]: ...

    async def expand_graph(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]: ...

    async def compare_revisions(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]: ...

    async def find_conflicts(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]: ...

    async def get_conflict(self, context: TrustedKnowledgeContext, conflict_group_id: str) -> dict[str, Any]: ...

    async def generate_update_report(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]: ...

    async def workflow_create(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]: ...

    async def list_workflows(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]: ...

    async def workflow_get(self, context: TrustedKnowledgeContext, workflow_run_id: str) -> dict[str, Any]: ...

    async def workflow_advance(self, context: TrustedKnowledgeContext, workflow_run_id: str) -> dict[str, Any]: ...

    async def workflow_generate_artifact(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]: ...

    async def list_artifacts(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]: ...

    async def get_artifact(self, context: TrustedKnowledgeContext, artifact_id: str) -> dict[str, Any]: ...

    async def approval_request(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]: ...

    async def approval_get(self, context: TrustedKnowledgeContext, approval_request_id: str) -> dict[str, Any]: ...

    async def list_approvals(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]: ...

    async def approval_decide(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]: ...

    async def action_preview(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]: ...

    async def action_execute(self, context: TrustedKnowledgeContext, approval_request_id: str) -> dict[str, Any]: ...

    async def validate_artifact(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]: ...

    async def validate_provenance(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]: ...

    async def validate_workflow(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]: ...

    async def validate_approval(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]: ...


class UnconfiguredKnowledgeServiceProvider:
    async def initialize(self) -> None:
        return None

    async def dispose(self) -> None:
        return None

    def _unavailable(self) -> None:
        raise KnowledgeServiceUnavailableError("Knowledge service provider is not configured")

    async def ingest(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]:
        self._unavailable()

    async def ingestion_status(self, context: TrustedKnowledgeContext, job_id: str) -> dict[str, Any]:
        self._unavailable()

    async def overview(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]:
        self._unavailable()

    async def search(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]:
        self._unavailable()

    async def analyze(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]:
        self._unavailable()

    async def get_source(self, context: TrustedKnowledgeContext, source_id: str) -> dict[str, Any]:
        self._unavailable()

    async def list_sources(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]:
        self._unavailable()

    async def get_source_detail(self, context: TrustedKnowledgeContext, source_id: str) -> dict[str, Any]:
        self._unavailable()

    async def list_source_revisions(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]:
        self._unavailable()

    async def get_revision(self, context: TrustedKnowledgeContext, revision_id: str) -> dict[str, Any]:
        self._unavailable()

    async def get_claims(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]:
        self._unavailable()

    async def expand_graph(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]:
        self._unavailable()

    async def compare_revisions(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]:
        self._unavailable()

    async def find_conflicts(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]:
        self._unavailable()

    async def get_conflict(self, context: TrustedKnowledgeContext, conflict_group_id: str) -> dict[str, Any]:
        self._unavailable()

    async def generate_update_report(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]:
        self._unavailable()

    async def workflow_create(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]:
        self._unavailable()

    async def list_workflows(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]:
        self._unavailable()

    async def workflow_get(self, context: TrustedKnowledgeContext, workflow_run_id: str) -> dict[str, Any]:
        self._unavailable()

    async def workflow_advance(self, context: TrustedKnowledgeContext, workflow_run_id: str) -> dict[str, Any]:
        self._unavailable()

    async def workflow_generate_artifact(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]:
        self._unavailable()

    async def list_artifacts(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]:
        self._unavailable()

    async def get_artifact(self, context: TrustedKnowledgeContext, artifact_id: str) -> dict[str, Any]:
        self._unavailable()

    async def approval_request(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]:
        self._unavailable()

    async def approval_get(self, context: TrustedKnowledgeContext, approval_request_id: str) -> dict[str, Any]:
        self._unavailable()

    async def list_approvals(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]:
        self._unavailable()

    async def approval_decide(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]:
        self._unavailable()

    async def action_preview(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]:
        self._unavailable()

    async def action_execute(self, context: TrustedKnowledgeContext, approval_request_id: str) -> dict[str, Any]:
        self._unavailable()

    async def validate_artifact(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]:
        self._unavailable()

    async def validate_provenance(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]:
        self._unavailable()

    async def validate_workflow(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]:
        self._unavailable()

    async def validate_approval(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]:
        self._unavailable()


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    return value


def _uuid(value: str, field_name: str) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} is invalid") from exc


class DatabaseKnowledgeServiceProvider:
    """Production provider that assembles Knowledge domain services lazily."""

    def __init__(self, config: KnowledgeDatabaseConfig) -> None:
        self._database = KnowledgeDatabase(config)

    @property
    def database(self) -> KnowledgeDatabase:
        return self._database

    async def initialize(self) -> None:
        await self._database.initialize()

    async def dispose(self) -> None:
        await self._database.dispose()

    @property
    def _session_factory(self):
        if self._database.session_factory is None:
            raise KnowledgeServiceUnavailableError("Knowledge service provider is not initialized")
        return self._database.session_factory

    async def ingest(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]:
        source_type = str(payload["source_type"])
        source_uri = str(payload["source_uri"])
        media_type = payload.get("media_type")
        metadata = payload.get("metadata") or {}
        display_name = None
        if source_type == "file":
            source_type = "upload_file"
        if source_type == "text":
            text_bytes = source_uri.encode("utf-8")
            digest = hashlib.sha256(text_bytes).hexdigest()
            display_name = f"text-{digest[:16]}.txt"
            uploads_dir = context.storage_root / "uploads"
            text_path = uploads_dir / display_name
            await asyncio.to_thread(uploads_dir.mkdir, parents=True, exist_ok=True)
            await asyncio.to_thread(text_path.write_bytes, text_bytes)
            source_type = "virtual_file"
            source_uri = f"/mnt/user-data/uploads/{display_name}"
            media_type = media_type or "text/plain"
            metadata = {**metadata, "source_kind": "text", "content_hash": digest}
        result = await IngestionPipeline(self._session_factory).ingest(
            workspace_id=context.workspace_id,
            source_input=SourceInput(
                kind=source_type,
                value=source_uri,
                thread_id=context.thread_id,
                user_id=context.user_id,
                display_name=display_name,
                media_type=media_type,
                metadata=metadata,
            ),
        )
        return _jsonable(result)

    async def ingestion_status(self, context: TrustedKnowledgeContext, job_id: str) -> dict[str, Any]:
        async with KnowledgeUnitOfWork(self._session_factory) as uow:
            assert uow.session is not None
            from deerflow.knowledge.models import IngestionJob

            job = await uow.session.get(IngestionJob, _uuid(job_id, "job_id"))
            if job is None or job.workspace_id != context.workspace_id:
                raise ValueError("IngestionJob does not belong to workspace")
            return {
                "job_id": str(job.id),
                "source_id": str(job.source_id) if job.source_id else None,
                "snapshot_id": str(job.snapshot_id) if job.snapshot_id else None,
                "revision_id": str(job.revision_id) if job.revision_id else None,
                "status": job.status.value,
                "error": job.error,
            }

    async def overview(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]:
        async with KnowledgeUnitOfWork(self._session_factory) as uow:
            assert uow.session is not None
            from deerflow.knowledge.models import (
                ApprovalRequest,
                Artifact,
                Claim,
                ConflictGroup,
                DocumentRevision,
                Entity,
                Relation,
                Source,
                WorkflowRun,
            )

            async def count(model: type) -> int:
                result = await uow.session.execute(select(func.count()).select_from(model).where(model.workspace_id == context.workspace_id))
                return int(result.scalar_one())

            recent_sources = await uow.sources.list_for_workspace(context.workspace_id, limit=5, offset=0)
            recent_artifacts = await uow.artifacts.list_for_workspace(context.workspace_id, limit=5, offset=0)
            pending_approvals = await uow.approval_requests.list_for_workspace(context.workspace_id, limit=5, offset=0)
            return {
                "stats": {
                    "sources": await count(Source),
                    "revisions": await count(DocumentRevision),
                    "claims": await count(Claim),
                    "entities": await count(Entity),
                    "relations": await count(Relation),
                    "conflicts": await count(ConflictGroup),
                    "workflows": await count(WorkflowRun),
                    "artifacts": await count(Artifact),
                    "approvals": await count(ApprovalRequest),
                },
                "recent_sources": [
                    {
                        "source_id": str(source.id),
                        "source_type": source.source_type,
                        "canonical_uri": source.canonical_uri,
                        "title": source.title,
                        "status": source.status.value,
                        "updated_at": source.updated_at.astimezone(UTC).isoformat(),
                    }
                    for source in recent_sources
                ],
                "running_jobs": [],
                "recent_artifacts": [
                    {
                        "artifact_id": str(artifact.id),
                        "artifact_type": artifact.artifact_type,
                        "title": artifact.title,
                        "validation_status": artifact.validation_status.value,
                        "staleness_status": artifact.staleness_status.value,
                        "created_at": artifact.created_at.astimezone(UTC).isoformat(),
                    }
                    for artifact in recent_artifacts
                ],
                "pending_approvals": [_approval_payload(row) for row in pending_approvals],
            }

    async def search(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]:
        result = await RetrievalService(self._session_factory).retrieve(
            workspace_id=context.workspace_id,
            query=str(payload["query"]),
            filters=payload.get("filters") or {},
            context_budget=int(payload.get("context_budget") or 4000),
        )
        return _jsonable(result)

    async def analyze(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]:
        context_budget = int(payload.get("context_budget") or 4000)
        evidence = await RetrievalService(self._session_factory).retrieve(
            workspace_id=context.workspace_id,
            query=str(payload["query"]),
            filters=payload.get("filters") or {},
            context_budget=context_budget,
        )
        result = await AnalysisService(model=DeterministicAnalysisModel()).analyze(
            workspace_id=context.workspace_id,
            query=str(payload["query"]),
            evidence_context_pack=evidence,
            context_budget=context_budget,
        )
        return _jsonable(result.model_dump())

    async def get_source(self, context: TrustedKnowledgeContext, source_id: str) -> dict[str, Any]:
        async with KnowledgeUnitOfWork(self._session_factory) as uow:
            source = await uow.sources.get_by_id(context.workspace_id, _uuid(source_id, "source_id"))
            if source is None:
                raise ValueError("Source does not belong to workspace")
            return {
                "source_id": str(source.id),
                "source_type": source.source_type,
                "canonical_uri": source.canonical_uri,
                "title": source.title,
                "latest_snapshot_id": str(source.latest_snapshot_id) if source.latest_snapshot_id else None,
                "status": source.status.value,
                "metadata": _jsonable(source.metadata_json or {}),
            }

    async def list_sources(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]:
        limit = min(int(payload.get("limit") or 50), 100)
        offset = max(int(payload.get("offset") or 0), 0)
        async with KnowledgeUnitOfWork(self._session_factory) as uow:
            rows = await uow.sources.list_for_workspace(context.workspace_id, limit=limit, offset=offset)
            return {
                "data": [
                    {
                        "source_id": str(source.id),
                        "source_type": source.source_type,
                        "canonical_uri": source.canonical_uri,
                        "title": source.title,
                        "status": source.status.value,
                        "latest_snapshot_id": str(source.latest_snapshot_id) if source.latest_snapshot_id else None,
                    }
                    for source in rows
                ],
                "pagination": {"limit": limit, "offset": offset},
            }

    async def list_source_revisions(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]:
        source_id = _uuid(str(payload["source_id"]), "source_id")
        limit = min(int(payload.get("limit") or 50), 100)
        offset = max(int(payload.get("offset") or 0), 0)
        async with KnowledgeUnitOfWork(self._session_factory) as uow:
            source = await uow.sources.get_by_id(context.workspace_id, source_id)
            if source is None:
                raise ValueError("Source does not belong to workspace")
            assert uow.session is not None
            from sqlalchemy import select

            from deerflow.knowledge.models import DocumentRevision

            result = await uow.session.execute(
                select(DocumentRevision).where(DocumentRevision.workspace_id == context.workspace_id, DocumentRevision.source_id == source_id).order_by(DocumentRevision.revision_number.desc()).limit(limit).offset(offset)
            )
            revisions = list(result.scalars().all())
            return {
                "data": [
                    {
                        "revision_id": str(revision.id),
                        "source_id": str(revision.source_id),
                        "snapshot_id": str(revision.snapshot_id),
                        "revision_number": revision.revision_number,
                        "parse_status": revision.parse_status.value,
                        "index_status": revision.index_status.value,
                    }
                    for revision in revisions
                ],
                "pagination": {"limit": limit, "offset": offset},
            }

    async def get_source_detail(self, context: TrustedKnowledgeContext, source_id: str) -> dict[str, Any]:
        source_uuid = _uuid(source_id, "source_id")
        async with KnowledgeUnitOfWork(self._session_factory) as uow:
            source = await uow.sources.get_by_id(context.workspace_id, source_uuid)
            if source is None:
                raise ValueError("Source does not belong to workspace")
            revisions = sorted(
                await uow.revisions.list_for_source(context.workspace_id, source_uuid),
                key=lambda revision: revision.revision_number,
                reverse=True,
            )
            revision_ids = [revision.id for revision in revisions]
            chunks = []
            evidence = []
            claims = []
            relations = []
            ingestion_jobs = []
            if revision_ids:
                assert uow.session is not None
                from deerflow.knowledge.models import Chunk, Claim, ClaimEvidenceLink, EvidenceSpan, IngestionJob, Relation

                chunk_result = await uow.session.execute(
                    select(Chunk).where(Chunk.workspace_id == context.workspace_id, Chunk.revision_id.in_(revision_ids)).order_by(Chunk.revision_id, Chunk.chunk_index)
                )
                chunk_rows = list(chunk_result.scalars().all())
                chunk_ids = [chunk.id for chunk in chunk_rows]
                chunks = [
                    {
                        "chunk_id": str(chunk.id),
                        "revision_id": str(chunk.revision_id),
                        "parent_chunk_id": str(chunk.parent_chunk_id) if chunk.parent_chunk_id else None,
                        "chunk_index": chunk.chunk_index,
                        "token_count": chunk.token_count,
                        "content": chunk.content,
                        "page_number": chunk.page_number,
                        "section_path": _jsonable(chunk.section_path or []),
                        "start_offset": chunk.start_offset,
                        "end_offset": chunk.end_offset,
                    }
                    for chunk in chunk_rows
                ]
                if chunk_ids:
                    evidence_result = await uow.session.execute(
                        select(EvidenceSpan).where(EvidenceSpan.workspace_id == context.workspace_id, EvidenceSpan.chunk_id.in_(chunk_ids)).order_by(EvidenceSpan.created_at)
                    )
                    evidence_rows = list(evidence_result.scalars().all())
                    evidence_ids = [span.id for span in evidence_rows]
                    evidence = [
                        {
                            "evidence_span_id": str(span.id),
                            "chunk_id": str(span.chunk_id),
                            "quoted_text": span.quoted_text,
                            "start_offset": span.start_offset,
                            "end_offset": span.end_offset,
                            "page_number": span.page_number,
                            "created_at": span.created_at.astimezone(UTC).isoformat(),
                        }
                        for span in evidence_rows
                    ]
                    if evidence_ids:
                        claim_result = await uow.session.execute(
                            select(Claim)
                            .join(ClaimEvidenceLink, ClaimEvidenceLink.claim_id == Claim.id)
                            .where(Claim.workspace_id == context.workspace_id, ClaimEvidenceLink.evidence_span_id.in_(evidence_ids))
                            .distinct()
                        )
                        claims = [
                            {
                                "claim_id": str(claim.id),
                                "claim_text": claim.claim_text,
                                "status": claim.status.value,
                                "stance": claim.stance.value,
                                "confidence": claim.confidence,
                            }
                            for claim in claim_result.scalars().all()
                        ]
                        relation_result = await uow.session.execute(
                            select(Relation).where(Relation.workspace_id == context.workspace_id, Relation.evidence_span_id.in_(evidence_ids)).distinct()
                        )
                        relations = [
                            {
                                "relation_id": str(relation.id),
                                "source_entity_id": str(relation.source_entity_id),
                                "target_entity_id": str(relation.target_entity_id),
                                "relation_type": relation.relation_type,
                                "evidence_span_id": str(relation.evidence_span_id),
                                "confidence": relation.confidence,
                            }
                            for relation in relation_result.scalars().all()
                        ]
                jobs_result = await uow.session.execute(
                    select(IngestionJob).where(IngestionJob.workspace_id == context.workspace_id, IngestionJob.source_id == source_uuid).order_by(IngestionJob.created_at.desc())
                )
                ingestion_jobs = [
                    {
                        "job_id": str(job.id),
                        "status": job.status.value,
                        "revision_id": str(job.revision_id) if job.revision_id else None,
                        "created_at": job.created_at.astimezone(UTC).isoformat(),
                        "completed_at": job.completed_at.astimezone(UTC).isoformat() if job.completed_at else None,
                        "error": job.error,
                    }
                    for job in jobs_result.scalars().all()
                ]
            return {
                "source": {
                    "source_id": str(source.id),
                    "source_type": source.source_type,
                    "canonical_uri": source.canonical_uri,
                    "title": source.title,
                    "author": source.author,
                    "latest_snapshot_id": str(source.latest_snapshot_id) if source.latest_snapshot_id else None,
                    "status": source.status.value,
                    "metadata": _jsonable(source.metadata_json or {}),
                    "created_at": source.created_at.astimezone(UTC).isoformat(),
                    "updated_at": source.updated_at.astimezone(UTC).isoformat(),
                },
                "revisions": [
                    {
                        "revision_id": str(revision.id),
                        "source_id": str(revision.source_id),
                        "snapshot_id": str(revision.snapshot_id),
                        "revision_number": revision.revision_number,
                        "previous_revision_id": str(revision.previous_revision_id) if revision.previous_revision_id else None,
                        "content_hash": revision.content_hash,
                        "parse_status": revision.parse_status.value,
                        "index_status": revision.index_status.value,
                        "created_at": revision.created_at.astimezone(UTC).isoformat(),
                    }
                    for revision in revisions
                ],
                "chunks": chunks,
                "claims": claims,
                "relations": relations,
                "evidence": evidence,
                "jobs": ingestion_jobs,
            }

    async def get_revision(self, context: TrustedKnowledgeContext, revision_id: str) -> dict[str, Any]:
        async with KnowledgeUnitOfWork(self._session_factory) as uow:
            revision = await uow.revisions.get_by_id(context.workspace_id, _uuid(revision_id, "revision_id"))
            if revision is None:
                raise ValueError("DocumentRevision does not belong to workspace")
            return {
                "revision_id": str(revision.id),
                "source_id": str(revision.source_id),
                "snapshot_id": str(revision.snapshot_id),
                "revision_number": revision.revision_number,
                "content_hash": revision.content_hash,
                "parse_status": revision.parse_status.value,
                "index_status": revision.index_status.value,
            }

    async def get_claims(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]:
        limit = min(int(payload.get("limit") or 50), 100)
        offset = max(int(payload.get("offset") or 0), 0)
        async with KnowledgeUnitOfWork(self._session_factory) as uow:
            rows = await uow.claims.list_for_workspace(context.workspace_id, limit=limit, offset=offset)
            return {
                "data": [
                    {
                        "claim_id": str(claim.id),
                        "claim_text": claim.claim_text,
                        "status": claim.status.value,
                        "stance": claim.stance.value,
                        "confidence": claim.confidence,
                    }
                    for claim in rows
                ],
                "pagination": {"limit": limit, "offset": offset},
            }

    async def expand_graph(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]:
        raise KnowledgeServiceUnavailableError("Knowledge graph service is not configured")

    async def compare_revisions(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]:
        old_revision_id = _uuid(str(payload.get("old_revision_id") or payload.get("base_revision_id")), "old_revision_id")
        new_revision_id = _uuid(str(payload.get("new_revision_id") or payload.get("target_revision_id")), "new_revision_id")
        async with KnowledgeUnitOfWork(self._session_factory) as uow:
            old_revision = await uow.revisions.get_by_id(context.workspace_id, old_revision_id)
            new_revision = await uow.revisions.get_by_id(context.workspace_id, new_revision_id)
            if old_revision is None or new_revision is None:
                raise ValueError("Revision does not belong to workspace")
            old_chunks = await uow.chunks.list_for_revision(context.workspace_id, old_revision_id)
            new_chunks = await uow.chunks.list_for_revision(context.workspace_id, new_revision_id)
            diff = diff_revisions(old_revision, new_revision, old_chunks, new_chunks)
            plan = build_incremental_processing_plan(diff)
            chunk_map = {chunk.id: chunk for chunk in [*old_chunks, *new_chunks]}
            return _revision_diff_payload(diff, plan, chunk_map)

    async def find_conflicts(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]:
        limit = min(int(payload.get("limit") or 50), 100)
        offset = max(int(payload.get("offset") or 0), 0)
        async with KnowledgeUnitOfWork(self._session_factory) as uow:
            assert uow.session is not None
            rows = await uow.conflict_groups.list_for_workspace(context.workspace_id, limit=limit, offset=offset)
            return {
                "data": [
                    await _conflict_payload(uow.session, context.workspace_id, row)
                    for row in rows
                ],
                "pagination": {"limit": limit, "offset": offset},
            }

    async def get_conflict(self, context: TrustedKnowledgeContext, conflict_group_id: str) -> dict[str, Any]:
        async with KnowledgeUnitOfWork(self._session_factory) as uow:
            assert uow.session is not None
            conflict = await uow.conflict_groups.get_by_id(context.workspace_id, _uuid(conflict_group_id, "conflict_group_id"))
            if conflict is None:
                raise ValueError("ConflictGroup does not belong to workspace")
            return await _conflict_payload(uow.session, context.workspace_id, conflict)

    async def generate_update_report(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]:
        new_revision_id = _uuid(str(payload.get("new_revision_id") or payload.get("revision_id")), "new_revision_id")
        async with KnowledgeUnitOfWork(self._session_factory) as uow:
            new_revision = await uow.revisions.get_by_id(context.workspace_id, new_revision_id)
            if new_revision is None:
                raise ValueError("Revision does not belong to workspace")
            old_revision_id = payload.get("old_revision_id") or payload.get("base_revision_id") or new_revision.previous_revision_id
            if old_revision_id is None:
                await _extract_revision_if_needed(self._session_factory, context.workspace_id, new_revision.id)
                return {
                    "status": "succeeded",
                    "source_id": str(new_revision.source_id),
                    "new_revision_id": str(new_revision.id),
                    "message": "Initial revision extracted; no previous revision is available for update comparison.",
                }
            old_uuid = _uuid(str(old_revision_id), "old_revision_id")
        await _extract_revision_if_needed(self._session_factory, context.workspace_id, old_uuid)
        report = await KnowledgeUpdateService(
            self._session_factory,
            extraction_processor=_DeterministicChunkProcessor(self._session_factory),
            indexing_processor=_NoopChunkProcessor(),
        ).process_revision_update(workspace_id=context.workspace_id, old_revision_id=old_uuid, new_revision_id=new_revision_id)
        return {
            **_jsonable(report),
            "markdown": render_markdown_report(report),
        }

    async def workflow_create(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]:
        raise KnowledgeServiceUnavailableError("Workflow handler services are not configured")

    async def list_workflows(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]:
        limit = min(int(payload.get("limit") or 50), 100)
        offset = max(int(payload.get("offset") or 0), 0)
        async with KnowledgeUnitOfWork(self._session_factory) as uow:
            rows = await uow.workflow_runs.list_for_workspace(context.workspace_id, limit=limit, offset=offset)
            return {
                "data": [
                    {
                        "workflow_run_id": str(run.id),
                        "workflow_type": run.workflow_type,
                        "status": run.status.value,
                        "current_step": run.current_step,
                        "input": _jsonable(run.input or {}),
                        "metadata": _jsonable(run.metadata_json or {}),
                        "created_at": run.created_at.astimezone(UTC).isoformat(),
                        "updated_at": run.updated_at.astimezone(UTC).isoformat(),
                        "completed_at": run.completed_at.astimezone(UTC).isoformat() if run.completed_at else None,
                        "error": run.error,
                    }
                    for run in rows
                ],
                "pagination": {"limit": limit, "offset": offset},
            }

    async def workflow_get(self, context: TrustedKnowledgeContext, workflow_run_id: str) -> dict[str, Any]:
        async with KnowledgeUnitOfWork(self._session_factory) as uow:
            run = await uow.workflow_runs.get_by_id(context.workspace_id, _uuid(workflow_run_id, "workflow_run_id"))
            if run is None:
                raise ValueError("WorkflowRun does not belong to workspace")
            steps = await uow.workflow_steps.list_for_workflow(context.workspace_id, run.id)
            return {
                "workflow_run_id": str(run.id),
                "workflow_type": run.workflow_type,
                "status": run.status.value,
                "current_step": run.current_step,
                "steps": [
                    {
                        "step_run_id": str(step.id),
                        "step_key": step.step_key,
                        "sequence": step.sequence,
                        "status": step.status.value,
                        "attempt": step.attempt,
                        "output_payload": _jsonable(step.output_payload or {}),
                    }
                    for step in steps
                ],
            }

    async def workflow_advance(self, context: TrustedKnowledgeContext, workflow_run_id: str) -> dict[str, Any]:
        raise KnowledgeServiceUnavailableError("Workflow handler services are not configured")

    async def workflow_generate_artifact(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]:
        raise KnowledgeServiceUnavailableError("Workflow artifact service is not configured")

    async def list_artifacts(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]:
        limit = min(int(payload.get("limit") or 50), 100)
        offset = max(int(payload.get("offset") or 0), 0)
        async with KnowledgeUnitOfWork(self._session_factory) as uow:
            rows = await uow.artifacts.list_for_workspace(context.workspace_id, limit=limit, offset=offset)
            return {
                "data": [
                    {
                        "artifact_id": str(row.id),
                        "artifact_type": row.artifact_type,
                        "title": row.title,
                        "status": row.validation_status.value,
                        "staleness_status": row.staleness_status.value,
                        "created_at": row.created_at.astimezone(UTC).isoformat(),
                    }
                    for row in rows
                ],
                "pagination": {"limit": limit, "offset": offset},
            }

    async def get_artifact(self, context: TrustedKnowledgeContext, artifact_id: str) -> dict[str, Any]:
        async with KnowledgeUnitOfWork(self._session_factory) as uow:
            artifact = await uow.artifacts.get_by_id(context.workspace_id, _uuid(artifact_id, "artifact_id"))
            if artifact is None:
                raise ValueError("Artifact does not belong to workspace")
            return {
                "artifact_id": str(artifact.id),
                "artifact_type": artifact.artifact_type,
                "title": artifact.title,
                "storage_path": artifact.storage_path,
                "validation_status": artifact.validation_status.value,
                "staleness_status": artifact.staleness_status.value,
                "metadata": _jsonable(artifact.metadata_json or {}),
            }

    async def approval_request(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]:
        async with KnowledgeUnitOfWork(self._session_factory) as uow:
            workflow = await uow.workflow_runs.get_by_id(context.workspace_id, _uuid(payload["workflow_run_id"], "workflow_run_id"))
            if workflow is None:
                raise ValueError("WorkflowRun does not belong to workspace")
            request = await uow.approval_requests.add(
                ApprovalRequest(
                    workspace_id=context.workspace_id,
                    workflow_run_id=workflow.id,
                    action_type=str(payload["action_type"]),
                    action_preview={
                        "target": payload.get("target"),
                        "payload": payload.get("payload") or {},
                        "preview": payload.get("preview") or {},
                        "source_step_run_id": payload.get("source_step_run_id"),
                        "artifact_ids": payload.get("artifact_ids") or [],
                        "evidence_ids": payload.get("evidence_ids") or [],
                    },
                    risk_level=RiskLevel(str(payload.get("risk_level") or RiskLevel.LOW.value)),
                    status=ApprovalStatus.AWAITING_APPROVAL if payload.get("requires_approval", True) else ApprovalStatus.APPROVED,
                )
            )
            await uow.commit()
            return {"approval_request_id": str(request.id), "status": request.status.value}

    async def approval_get(self, context: TrustedKnowledgeContext, approval_request_id: str) -> dict[str, Any]:
        async with KnowledgeUnitOfWork(self._session_factory) as uow:
            request = await uow.approval_requests.get_by_id(context.workspace_id, _uuid(approval_request_id, "approval_request_id"))
            if request is None:
                raise ValueError("ApprovalRequest does not belong to workspace")
            return _approval_payload(request)

    async def list_approvals(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]:
        limit = min(int(payload.get("limit") or 50), 100)
        offset = max(int(payload.get("offset") or 0), 0)
        async with KnowledgeUnitOfWork(self._session_factory) as uow:
            rows = await uow.approval_requests.list_for_workspace(context.workspace_id, limit=limit, offset=offset)
            return {"data": [_approval_payload(row) for row in rows], "pagination": {"limit": limit, "offset": offset}}

    async def approval_decide(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]:
        status_by_decision = {
            "approve": ApprovalStatus.APPROVED,
            "reject": ApprovalStatus.REJECTED,
            "cancel": ApprovalStatus.CANCELLED,
        }
        decision = str(payload["decision"])
        if decision not in status_by_decision:
            raise ValueError("approval decision is invalid")
        async with KnowledgeUnitOfWork(self._session_factory) as uow:
            request = await uow.approval_requests.get_by_id(context.workspace_id, _uuid(payload["approval_request_id"], "approval_request_id"))
            if request is None:
                raise ValueError("ApprovalRequest does not belong to workspace")
            request.status = status_by_decision[decision]
            request.decided_by = context.actor_id
            request.decided_at = datetime.now(UTC)
            await uow.commit()
            return _approval_payload(request)

    async def action_preview(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("approval_request_id"):
            approval = await self.approval_get(context, str(payload["approval_request_id"]))
            return {"side_effect": False, "approval": approval}
        return {"side_effect": False, "preview": payload.get("action_draft") or {}}

    async def action_execute(self, context: TrustedKnowledgeContext, approval_request_id: str) -> dict[str, Any]:
        async with KnowledgeUnitOfWork(self._session_factory) as uow:
            request = await uow.approval_requests.get_by_id(context.workspace_id, _uuid(approval_request_id, "approval_request_id"))
            if request is None:
                raise ValueError("ApprovalRequest does not belong to workspace")
            if request.status != ApprovalStatus.APPROVED:
                raise ValueError("ApprovalRequest is not approved")
            raise KnowledgeServiceUnavailableError("Action execution adapters are not configured")

    async def validate_artifact(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]:
        raise KnowledgeServiceUnavailableError("Artifact validation service is not configured")

    async def validate_provenance(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]:
        raise KnowledgeServiceUnavailableError("Provenance validation service is not configured")

    async def validate_workflow(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]:
        raise KnowledgeServiceUnavailableError("Workflow validation service is not configured")

    async def validate_approval(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]:
        approval = await self.approval_get(context, str(payload["approval_request_id"]))
        return {"issues": [] if approval["status"] == ApprovalStatus.APPROVED.value else ["ApprovalRequest is not approved"]}


def _revision_diff_payload(diff: RevisionDiff, plan: IncrementalProcessingPlan, chunks_by_id: dict[UUID, Chunk]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for pair in diff.unchanged_pairs:
        items.append(_paired_change_payload(ChunkChangeType.UNCHANGED, pair.old_chunk_id, pair.new_chunk_id, chunks_by_id))
    for chunk_id in diff.added_chunk_ids:
        items.append(_single_change_payload(ChunkChangeType.ADDED, None, chunk_id, chunks_by_id))
    for chunk_id in diff.removed_chunk_ids:
        items.append(_single_change_payload(ChunkChangeType.REMOVED, chunk_id, None, chunks_by_id))
    for pair in diff.modified_pairs:
        items.append(_paired_change_payload(ChunkChangeType.MODIFIED, pair.old_chunk_id, pair.new_chunk_id, chunks_by_id))
    for pair in diff.moved_pairs:
        items.append(_paired_change_payload(ChunkChangeType.MOVED, pair.old_chunk_id, pair.new_chunk_id, chunks_by_id))
    return {
        "old_revision_id": str(diff.old_revision_id),
        "new_revision_id": str(diff.new_revision_id),
        "summary": _jsonable(diff.summary),
        "changes": items,
        "incremental_plan": {
            "reprocess_chunk_ids": [str(item) for item in plan.reprocess_chunk_ids],
            "reused_chunk_ids": [str(item) for item in plan.reused_chunk_ids],
            "removed_chunk_ids": [str(item) for item in plan.removed_chunk_ids],
        },
    }


def _paired_change_payload(change_type: ChunkChangeType, old_chunk_id: UUID, new_chunk_id: UUID, chunks_by_id: dict[UUID, Chunk]) -> dict[str, Any]:
    return _single_change_payload(change_type, old_chunk_id, new_chunk_id, chunks_by_id)


def _single_change_payload(change_type: ChunkChangeType, old_chunk_id: UUID | None, new_chunk_id: UUID | None, chunks_by_id: dict[UUID, Chunk]) -> dict[str, Any]:
    old_chunk = chunks_by_id.get(old_chunk_id) if old_chunk_id else None
    new_chunk = chunks_by_id.get(new_chunk_id) if new_chunk_id else None
    return {
        "change_type": change_type.name,
        "old_chunk_id": str(old_chunk_id) if old_chunk_id else None,
        "new_chunk_id": str(new_chunk_id) if new_chunk_id else None,
        "old_chunk": _chunk_payload(old_chunk) if old_chunk else None,
        "new_chunk": _chunk_payload(new_chunk) if new_chunk else None,
    }


def _chunk_payload(chunk: Chunk) -> dict[str, Any]:
    return {
        "chunk_id": str(chunk.id),
        "revision_id": str(chunk.revision_id),
        "parent_chunk_id": str(chunk.parent_chunk_id) if chunk.parent_chunk_id else None,
        "chunk_index": chunk.chunk_index,
        "token_count": chunk.token_count,
        "content": chunk.content,
        "page_number": chunk.page_number,
        "section_path": _jsonable(chunk.section_path or []),
        "start_offset": chunk.start_offset,
        "end_offset": chunk.end_offset,
    }


async def _conflict_payload(session: AsyncSession, workspace_id: UUID, conflict: ConflictGroup) -> dict[str, Any]:
    from deerflow.knowledge.models import ConflictGroupClaim

    linked_claims = list(
        (
            await session.execute(
                select(Claim)
                .join(ConflictGroupClaim, (ConflictGroupClaim.claim_id == Claim.id) & (ConflictGroupClaim.workspace_id == Claim.workspace_id))
                .where(
                    ConflictGroupClaim.workspace_id == workspace_id,
                    ConflictGroupClaim.conflict_group_id == conflict.id,
                )
                .order_by(Claim.updated_at, Claim.id)
            )
        ).scalars()
    )
    claim_payloads = [await _claim_payload_with_citations(session, workspace_id, claim) for claim in linked_claims]
    claim_ids = [claim.id for claim in linked_claims]
    affected_artifacts = await _affected_artifacts_for_claims(session, workspace_id, claim_ids)
    metadata = conflict.metadata_json or {}
    classification = str(metadata.get("classification") or "possible_conflict").upper()
    basis = str(metadata.get("basis") or conflict.summary or "Claims require review.")
    active_claim_id = next((payload["claim_id"] for payload in reversed(claim_payloads) if payload["status"] == ClaimStatus.ACTIVE.value), None)
    citation_ids = sorted({citation["evidence_span_id"] for payload in claim_payloads for citation in payload["citations"]})
    sources = sorted({citation["source_id"] for payload in claim_payloads for citation in payload["citations"] if citation["source_id"]})
    return {
        "conflict_group_id": str(conflict.id),
        "topic": conflict.topic,
        "status": conflict.status.value,
        "classification": classification,
        "summary": conflict.summary or basis,
        "basis": basis,
        "claims": claim_payloads,
        "claim_ids": [str(claim_id) for claim_id in claim_ids],
        "source_ids": sources,
        "citation_ids": citation_ids,
        "active_claim_id": active_claim_id,
        "affected_artifacts": affected_artifacts,
        "affected_artifact_ids": [item["artifact_id"] for item in affected_artifacts],
        "scope_or_condition": str(metadata.get("scope_or_condition") or basis),
        "recommended_next_step": _conflict_recommendation(classification),
        "metadata": _jsonable(metadata),
        "created_at": conflict.created_at.astimezone(UTC).isoformat(),
        "updated_at": conflict.updated_at.astimezone(UTC).isoformat(),
    }


async def _claim_payload_with_citations(session: AsyncSession, workspace_id: UUID, claim: Claim) -> dict[str, Any]:
    from deerflow.knowledge.models import ClaimEvidenceLink, DocumentRevision, EvidenceSpan, Source

    citations = list(
        (
            await session.execute(
                select(EvidenceSpan, Chunk, DocumentRevision, Source)
                .join(ClaimEvidenceLink, (ClaimEvidenceLink.evidence_span_id == EvidenceSpan.id) & (ClaimEvidenceLink.workspace_id == EvidenceSpan.workspace_id))
                .join(Chunk, (Chunk.id == EvidenceSpan.chunk_id) & (Chunk.workspace_id == EvidenceSpan.workspace_id))
                .join(DocumentRevision, (DocumentRevision.id == Chunk.revision_id) & (DocumentRevision.workspace_id == Chunk.workspace_id))
                .join(Source, (Source.id == DocumentRevision.source_id) & (Source.workspace_id == DocumentRevision.workspace_id))
                .where(
                    ClaimEvidenceLink.workspace_id == workspace_id,
                    ClaimEvidenceLink.claim_id == claim.id,
                )
                .order_by(EvidenceSpan.created_at, EvidenceSpan.id)
            )
        ).all()
    )
    return {
        "claim_id": str(claim.id),
        "claim_text": claim.claim_text,
        "normalized_subject": claim.normalized_subject,
        "predicate": claim.predicate,
        "normalized_object": claim.normalized_object,
        "stance": claim.stance.value,
        "status": claim.status.value,
        "confidence": claim.confidence,
        "valid_from": claim.valid_from.astimezone(UTC).isoformat() if claim.valid_from else None,
        "valid_to": claim.valid_to.astimezone(UTC).isoformat() if claim.valid_to else None,
        "metadata": _jsonable(claim.metadata_json or {}),
        "citations": [_citation_payload(span, chunk, revision, source) for span, chunk, revision, source in citations],
    }


def _citation_payload(span: Any, chunk: Chunk, revision: Any, source: Any) -> dict[str, Any]:
    return {
        "evidence_span_id": str(span.id),
        "citation_id": str(span.id),
        "chunk_id": str(chunk.id),
        "revision_id": str(revision.id),
        "revision_number": revision.revision_number,
        "source_id": str(source.id),
        "source_title": source.title,
        "source_uri": source.canonical_uri,
        "quoted_text": span.quoted_text,
        "start_offset": span.start_offset,
        "end_offset": span.end_offset,
        "page_number": span.page_number,
        "section_path": _jsonable(chunk.section_path or []),
    }


async def _affected_artifacts_for_claims(session: AsyncSession, workspace_id: UUID, claim_ids: list[UUID]) -> list[dict[str, Any]]:
    if not claim_ids:
        return []
    from deerflow.knowledge.models import Artifact, ArtifactEvidenceLink

    rows = list(
        (
            await session.execute(
                select(Artifact)
                .join(ArtifactEvidenceLink, (ArtifactEvidenceLink.artifact_id == Artifact.id) & (ArtifactEvidenceLink.workspace_id == Artifact.workspace_id))
                .where(
                    Artifact.workspace_id == workspace_id,
                    ArtifactEvidenceLink.claim_id.in_(claim_ids),
                )
                .distinct()
                .order_by(Artifact.updated_at.desc(), Artifact.id)
            )
        ).scalars()
    )
    return [
        {
            "artifact_id": str(artifact.id),
            "artifact_type": artifact.artifact_type,
            "title": artifact.title,
            "staleness_status": artifact.staleness_status.value,
            "stale_reasons": _jsonable((artifact.metadata_json or {}).get("staleness_reasons") or []),
        }
        for artifact in rows
    ]


def _conflict_recommendation(classification: str) -> str:
    if classification == "TEMPORAL_UPDATE":
        return "Review the newer citation and decide whether it should supersede the previous claim."
    if classification == "DIRECT_CONTRADICTION":
        return "Review both cited claims and choose which claim remains active."
    if classification == "SOURCE_DISAGREEMENT":
        return "Compare source authority and keep the better-supported claim active."
    return "Review the cited evidence before using affected claims in artifacts."


async def _extract_revision_if_needed(session_factory: SessionFactory, workspace_id: UUID, revision_id: UUID) -> None:
    result = await ExtractionService(session_factory, model=DeterministicStructuredExtractionModel()).extract_revision(
        workspace_id=workspace_id,
        revision_id=revision_id,
    )
    if result.status != JobStatus.SUCCEEDED:
        raise RuntimeError("Deterministic extraction failed for revision")


class _DeterministicChunkProcessor:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory
        self._model = DeterministicStructuredExtractionModel()
        self._validator = ExtractionValidator()
        self._persistence = ExtractionPersistence()

    async def process_chunk(self, *, workspace_id: UUID, revision_id: UUID, chunk_id: UUID) -> None:
        async with KnowledgeUnitOfWork(self._session_factory) as uow:
            assert uow.session is not None
            chunk = await uow.chunks.get_by_id(workspace_id, chunk_id)
            if chunk is None or chunk.revision_id != revision_id:
                raise ValueError("Chunk does not belong to revision")
            run = ExtractionRun(
                id=uuid4(),
                workspace_id=workspace_id,
                revision_id=revision_id,
                model_name=self._model.model_identity,
                prompt_version="incremental",
                status=JobStatus.RUNNING,
                metadata_json={"model_identity": self._model.model_identity, "scope": "incremental_chunk"},
            )
            uow.session.add(run)
            await uow.session.flush()
            output = await self._model.extract(
                ModelExtractionRequest(
                    workspace_id=workspace_id,
                    revision_id=revision_id,
                    chunk_id=chunk.id,
                    chunk_text=chunk.content,
                    page_number=chunk.page_number,
                    section_path=[str(part) for part in (chunk.section_path or [])],
                )
            )
            chunk_text = ChunkText(
                id=chunk.id,
                revision_id=chunk.revision_id,
                workspace_id=chunk.workspace_id,
                content=chunk.content,
                page_number=chunk.page_number,
                section_path=[str(part) for part in (chunk.section_path or [])],
            )
            validated = self._validator.validate(output, [chunk_text], workspace_id)
            counts = await self._persistence.persist_chunk_output(
                uow.session,
                workspace_id=workspace_id,
                extraction_run_id=run.id,
                output=validated.output,
                chunks_by_id={chunk.id: chunk},
            )
            run.status = JobStatus.SUCCEEDED
            run.completed_at = datetime.now(UTC)
            run.metadata_json = {
                **(run.metadata_json or {}),
                "processed_chunk_count": 1,
                "entity_count": counts.entity_count,
                "claim_count": counts.claim_count,
                "relation_count": counts.relation_count,
                "rejected_item_count": validated.rejected_item_count,
                "warnings": [issue.message for issue in validated.issues],
            }
            await uow.commit()


class _NoopChunkProcessor:
    async def process_chunk(self, *, workspace_id: UUID, revision_id: UUID, chunk_id: UUID) -> None:
        return None


def _approval_payload(request: ApprovalRequest) -> dict[str, Any]:
    return {
        "approval_request_id": str(request.id),
        "workflow_run_id": str(request.workflow_run_id),
        "action_type": request.action_type,
        "status": request.status.value,
        "risk_level": request.risk_level.value,
        "decided_by": request.decided_by,
        "decided_at": request.decided_at.astimezone(UTC).isoformat() if request.decided_at else None,
        "action_preview": _jsonable(request.action_preview or {}),
    }


def build_database_knowledge_service_provider(database_url: str) -> DatabaseKnowledgeServiceProvider:
    return DatabaseKnowledgeServiceProvider(KnowledgeDatabaseConfig(database_url=SecretStr(database_url)))


def _runtime_context(runtime: Any | None) -> dict:
    if runtime is None:
        return {}
    context = getattr(runtime, "context", None)
    return context if isinstance(context, dict) else {}


_provider: KnowledgeServiceProvider = UnconfiguredKnowledgeServiceProvider()


def get_knowledge_service_provider() -> KnowledgeServiceProvider:
    return _provider


def set_knowledge_service_provider(provider: KnowledgeServiceProvider) -> None:
    global _provider
    _provider = provider


def reset_knowledge_service_provider() -> None:
    global _provider
    _provider = UnconfiguredKnowledgeServiceProvider()


def resolve_knowledge_service_provider(runtime: Any | None = None) -> KnowledgeServiceProvider:
    """Resolve the configured provider without requiring callers to monkeypatch.

    The Gateway/runtime lifecycle can either install a provider explicitly via
    ``set_knowledge_service_provider`` or place a trusted ``knowledge_database_url``
    in runtime context. The latter creates a disposable database-backed provider
    lazily on first Knowledge Tool use.
    """

    global _provider
    if not isinstance(_provider, UnconfiguredKnowledgeServiceProvider):
        return _provider
    context = _runtime_context(runtime)
    injected = context.get("knowledge_service_provider")
    if injected is not None:
        _provider = injected
        return _provider
    database_url = context.get("knowledge_database_url")
    if database_url:
        _provider = build_database_knowledge_service_provider(str(database_url))
    return _provider
