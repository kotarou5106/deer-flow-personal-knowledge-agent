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

from deerflow.config.paths import get_paths
from deerflow.knowledge.analysis import AnalysisService
from deerflow.knowledge.analysis.model_client import DeterministicAnalysisModel
from deerflow.knowledge.config import KnowledgeDatabaseConfig
from deerflow.knowledge.database import KnowledgeDatabase
from deerflow.knowledge.enums import ApprovalStatus, ClaimStatus, JobStatus, RiskLevel, WorkflowStatus
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
from deerflow.knowledge.workflows import (
    ArtifactWriteRequest,
    ArtifactWriteResult,
    HandlerRegistry,
    StepHandlerContext,
    StepHandlerResult,
    StepOutputKind,
    WorkflowArtifactService,
    WorkflowEngine,
    WorkflowType,
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

    async def workflow_pause(self, context: TrustedKnowledgeContext, workflow_run_id: str) -> dict[str, Any]: ...

    async def workflow_resume(self, context: TrustedKnowledgeContext, workflow_run_id: str) -> dict[str, Any]: ...

    async def workflow_retry(self, context: TrustedKnowledgeContext, workflow_run_id: str) -> dict[str, Any]: ...

    async def workflow_generate_artifact(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]: ...

    async def list_artifacts(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]: ...

    async def get_artifact(self, context: TrustedKnowledgeContext, artifact_id: str) -> dict[str, Any]: ...

    async def list_artifact_evidence_links(self, context: TrustedKnowledgeContext, artifact_id: str) -> dict[str, Any]: ...

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

    async def workflow_pause(self, context: TrustedKnowledgeContext, workflow_run_id: str) -> dict[str, Any]:
        self._unavailable()

    async def workflow_resume(self, context: TrustedKnowledgeContext, workflow_run_id: str) -> dict[str, Any]:
        self._unavailable()

    async def workflow_retry(self, context: TrustedKnowledgeContext, workflow_run_id: str) -> dict[str, Any]:
        self._unavailable()

    async def workflow_generate_artifact(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]:
        self._unavailable()

    async def list_artifacts(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]:
        self._unavailable()

    async def get_artifact(self, context: TrustedKnowledgeContext, artifact_id: str) -> dict[str, Any]:
        self._unavailable()

    async def list_artifact_evidence_links(self, context: TrustedKnowledgeContext, artifact_id: str) -> dict[str, Any]:
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

                chunk_result = await uow.session.execute(select(Chunk).where(Chunk.workspace_id == context.workspace_id, Chunk.revision_id.in_(revision_ids)).order_by(Chunk.revision_id, Chunk.chunk_index))
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
                    evidence_result = await uow.session.execute(select(EvidenceSpan).where(EvidenceSpan.workspace_id == context.workspace_id, EvidenceSpan.chunk_id.in_(chunk_ids)).order_by(EvidenceSpan.created_at))
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
                            select(Claim).join(ClaimEvidenceLink, ClaimEvidenceLink.claim_id == Claim.id).where(Claim.workspace_id == context.workspace_id, ClaimEvidenceLink.evidence_span_id.in_(evidence_ids)).distinct()
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
                        relation_result = await uow.session.execute(select(Relation).where(Relation.workspace_id == context.workspace_id, Relation.evidence_span_id.in_(evidence_ids)).distinct())
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
                jobs_result = await uow.session.execute(select(IngestionJob).where(IngestionJob.workspace_id == context.workspace_id, IngestionJob.source_id == source_uuid).order_by(IngestionJob.created_at.desc()))
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
                "data": [await _conflict_payload(uow.session, context.workspace_id, row) for row in rows],
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
        input_payload = dict(payload.get("input") or payload.get("input_payload") or {})
        input_payload["user_id"] = context.user_id
        input_payload["thread_id"] = context.thread_id
        result = await self._workflow_engine(context).create(
            workspace_id=context.workspace_id,
            workflow_type=str(payload["workflow_type"]),
            input_payload=input_payload,
            idempotency_key=payload.get("idempotency_key"),
        )
        return await self.workflow_get(context, str(result.workflow_run_id))

    async def list_workflows(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]:
        limit = min(int(payload.get("limit") or 50), 100)
        offset = max(int(payload.get("offset") or 0), 0)
        async with KnowledgeUnitOfWork(self._session_factory) as uow:
            assert uow.session is not None
            from deerflow.knowledge.models import WorkflowArtifact

            rows = await uow.workflow_runs.list_for_workspace(context.workspace_id, limit=limit, offset=offset)
            data = []
            for run in rows:
                steps = await uow.workflow_steps.list_for_workflow(context.workspace_id, run.id)
                artifact_ids = [
                    str(row)
                    for row in (
                        await uow.session.execute(
                            select(WorkflowArtifact.artifact_id).where(
                                WorkflowArtifact.workspace_id == context.workspace_id,
                                WorkflowArtifact.workflow_run_id == run.id,
                            )
                        )
                    ).scalars()
                ]
                data.append(
                    {
                        "workflow_run_id": str(run.id),
                        "workflow_type": run.workflow_type,
                        "status": run.status.value,
                        "current_step": run.current_step,
                        "input": _jsonable(run.input or {}),
                        "metadata": _jsonable(run.metadata_json or {}),
                        "artifact_ids": artifact_ids,
                        "steps": [_workflow_step_payload(step) for step in steps],
                        "created_at": run.created_at.astimezone(UTC).isoformat(),
                        "updated_at": run.updated_at.astimezone(UTC).isoformat(),
                        "completed_at": run.completed_at.astimezone(UTC).isoformat() if run.completed_at else None,
                        "error": run.error,
                    }
                )
            return {
                "data": data,
                "pagination": {"limit": limit, "offset": offset},
            }

    async def workflow_get(self, context: TrustedKnowledgeContext, workflow_run_id: str) -> dict[str, Any]:
        async with KnowledgeUnitOfWork(self._session_factory) as uow:
            run = await uow.workflow_runs.get_by_id(context.workspace_id, _uuid(workflow_run_id, "workflow_run_id"))
            if run is None:
                raise ValueError("WorkflowRun does not belong to workspace")
            steps = await uow.workflow_steps.list_for_workflow(context.workspace_id, run.id)
            assert uow.session is not None
            from deerflow.knowledge.models import WorkflowArtifact

            artifact_ids = [
                str(row)
                for row in (
                    await uow.session.execute(
                        select(WorkflowArtifact.artifact_id).where(
                            WorkflowArtifact.workspace_id == context.workspace_id,
                            WorkflowArtifact.workflow_run_id == run.id,
                        )
                    )
                ).scalars()
            ]
            return {
                "workflow_run_id": str(run.id),
                "workflow_type": run.workflow_type,
                "status": run.status.value,
                "current_step": run.current_step,
                "input": _jsonable(run.input or {}),
                "metadata": _jsonable(run.metadata_json or {}),
                "artifact_ids": artifact_ids,
                "created_at": run.created_at.astimezone(UTC).isoformat(),
                "updated_at": run.updated_at.astimezone(UTC).isoformat(),
                "completed_at": run.completed_at.astimezone(UTC).isoformat() if run.completed_at else None,
                "error": run.error,
                "steps": [_workflow_step_payload(step) for step in steps],
            }

    async def workflow_advance(self, context: TrustedKnowledgeContext, workflow_run_id: str) -> dict[str, Any]:
        result = await self._workflow_engine(context).advance(workspace_id=context.workspace_id, workflow_run_id=_uuid(workflow_run_id, "workflow_run_id"))
        return await self.workflow_get(context, str(result.workflow_run_id))

    async def workflow_pause(self, context: TrustedKnowledgeContext, workflow_run_id: str) -> dict[str, Any]:
        result = await self._workflow_engine(context).pause(workspace_id=context.workspace_id, workflow_run_id=_uuid(workflow_run_id, "workflow_run_id"))
        return await self.workflow_get(context, str(result.workflow_run_id))

    async def workflow_resume(self, context: TrustedKnowledgeContext, workflow_run_id: str) -> dict[str, Any]:
        result = await self._workflow_engine(context).resume(workspace_id=context.workspace_id, workflow_run_id=_uuid(workflow_run_id, "workflow_run_id"))
        return await self.workflow_get(context, str(result.workflow_run_id))

    async def workflow_retry(self, context: TrustedKnowledgeContext, workflow_run_id: str) -> dict[str, Any]:
        result = await self._workflow_engine(context).retry_failed_step(workspace_id=context.workspace_id, workflow_run_id=_uuid(workflow_run_id, "workflow_run_id"))
        return await self.workflow_get(context, str(result.workflow_run_id))

    async def workflow_generate_artifact(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]:
        workflow_run_id = _uuid(str(payload["workflow_run_id"]), "workflow_run_id")
        artifact = await _persist_workflow_artifact_from_state(
            self._session_factory,
            context,
            workflow_run_id,
            idempotency_key=payload.get("idempotency_key"),
        )
        return await self.get_artifact(context, str(artifact.artifact_id))

    def _workflow_engine(self, context: TrustedKnowledgeContext) -> WorkflowEngine:
        return WorkflowEngine(self._session_factory, handlers=_deterministic_workflow_handlers(self._session_factory, context))

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
                        "validation_status": row.validation_status.value,
                        "staleness_status": row.staleness_status.value,
                        "workflow_run_id": str((row.metadata_json or {}).get("workflow_run_id") or ""),
                        "metadata": _jsonable(row.metadata_json or {}),
                        "created_at": row.created_at.astimezone(UTC).isoformat(),
                        "updated_at": row.updated_at.astimezone(UTC).isoformat(),
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
            assert uow.session is not None
            evidence_links = await _artifact_evidence_link_payloads(uow.session, context.workspace_id, artifact.id)
            return {
                "artifact_id": str(artifact.id),
                "artifact_type": artifact.artifact_type,
                "title": artifact.title,
                "storage_path": artifact.storage_path,
                "validation_status": artifact.validation_status.value,
                "staleness_status": artifact.staleness_status.value,
                "workflow_run_id": str((artifact.metadata_json or {}).get("workflow_run_id") or ""),
                "markdown": _read_artifact_markdown(context, artifact.metadata_json or {}),
                "evidence_links": evidence_links,
                "metadata": _jsonable(artifact.metadata_json or {}),
                "created_at": artifact.created_at.astimezone(UTC).isoformat(),
                "updated_at": artifact.updated_at.astimezone(UTC).isoformat(),
            }

    async def list_artifact_evidence_links(self, context: TrustedKnowledgeContext, artifact_id: str) -> dict[str, Any]:
        async with KnowledgeUnitOfWork(self._session_factory) as uow:
            artifact = await uow.artifacts.get_by_id(context.workspace_id, _uuid(artifact_id, "artifact_id"))
            if artifact is None:
                raise ValueError("Artifact does not belong to workspace")
            assert uow.session is not None
            return {"data": await _artifact_evidence_link_payloads(uow.session, context.workspace_id, artifact.id)}

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


def _workflow_step_payload(step: Any) -> dict[str, Any]:
    return {
        "step_run_id": str(step.id),
        "step_key": step.step_key,
        "sequence": step.sequence,
        "status": step.status.value,
        "attempt": step.attempt,
        "input_payload": _jsonable(step.input_payload or {}),
        "output_payload": _jsonable(step.output_payload or {}),
        "started_at": step.started_at.astimezone(UTC).isoformat() if step.started_at else None,
        "completed_at": step.completed_at.astimezone(UTC).isoformat() if step.completed_at else None,
        "error_type": step.error_type,
        "error_message": step.error_message,
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


def _deterministic_workflow_handlers(session_factory: SessionFactory, context: TrustedKnowledgeContext) -> HandlerRegistry:
    handler = _DeterministicWorkflowHandler(session_factory, context)
    return HandlerRegistry(
        {
            "retrieve_evidence": handler.retrieve_evidence,
            "analyze_evidence": handler.analyze_evidence,
            "review_knowledge_update": handler.review_knowledge_update,
            "create_action_draft": handler.create_action_draft,
            "persist_artifact": handler.persist_artifact,
        }
    )


class _DeterministicWorkflowHandler:
    def __init__(self, session_factory: SessionFactory, context: TrustedKnowledgeContext) -> None:
        self._session_factory = session_factory
        self._context = context

    async def retrieve_evidence(self, step_context: StepHandlerContext) -> StepHandlerResult:
        workflow_input = dict(step_context.input_payload.get("workflow_input") or {})
        source_ids = _source_ids_from_workflow_input(workflow_input)
        revision_ids = await _latest_revision_ids(self._session_factory, self._context.workspace_id, source_ids)
        for revision_id in revision_ids:
            await _extract_revision_if_needed(self._session_factory, self._context.workspace_id, revision_id)
        evidence_items = await _workflow_evidence_items(self._session_factory, self._context.workspace_id, revision_ids)
        return StepHandlerResult(
            {
                "evidence_items": evidence_items,
                "evidence_span_ids": [item["evidence_span_id"] for item in evidence_items if item.get("evidence_span_id")],
                "claim_ids": [item["claim_id"] for item in evidence_items if item.get("claim_id")],
                "revision_ids": [str(item) for item in revision_ids],
            }
        )

    async def analyze_evidence(self, step_context: StepHandlerContext) -> StepHandlerResult:
        workflow_input = dict(step_context.input_payload.get("workflow_input") or {})
        evidence_items = list((step_context.previous_outputs.get("retrieve_evidence") or {}).get("evidence_items") or [])
        workflow_type = await _workflow_type_for_run(self._session_factory, self._context.workspace_id, step_context.workflow_run_id)
        sections = _workflow_sections(workflow_type, workflow_input, evidence_items)
        return StepHandlerResult({"sections": sections, "evidence_count": len(evidence_items)})

    async def review_knowledge_update(self, step_context: StepHandlerContext) -> StepHandlerResult:
        workflow_input = dict(step_context.input_payload.get("workflow_input") or {})
        sections = {
            "Executive Summary": "Knowledge update review is ready for human review.",
            "Decision Context": f"Source {workflow_input.get('source_id', 'unknown')} changed.",
            "Evidence": "Review the linked revision diff and conflicts.",
            "Recommendation": "Keep stale artifacts visible and review affected claims before reuse.",
            "Open Questions": "Confirm whether downstream artifacts should be regenerated.",
        }
        return StepHandlerResult({"sections": sections, "evidence_count": 0})

    async def create_action_draft(self, step_context: StepHandlerContext) -> StepHandlerResult:
        workflow_input = dict(step_context.input_payload.get("workflow_input") or {})
        objective = str(workflow_input.get("objective") or "Follow up on knowledge evidence")
        return StepHandlerResult(
            {
                "action_draft": {
                    "objective": objective,
                    "proposed_action": "draft_follow_up",
                    "parameters_preview": {"title": objective},
                    "risk": str(workflow_input.get("risk_level") or "low"),
                    "requires_approval": True,
                    "executed": False,
                }
            },
            output_kind=StepOutputKind.ACTION_DRAFT,
            requires_approval=True,
        )

    async def persist_artifact(self, step_context: StepHandlerContext) -> StepHandlerResult:
        result = await _persist_workflow_artifact_from_state(self._session_factory, self._context, step_context.workflow_run_id)
        return StepHandlerResult(
            {
                "artifact_id": str(result.artifact_id),
                "storage_path": result.storage_path,
                "markdown_storage_path": result.markdown_storage_path,
                "evidence_link_count": result.evidence_link_count,
            },
            output_kind=StepOutputKind.ARTIFACT_REQUEST,
        )


def _source_ids_from_workflow_input(workflow_input: dict[str, Any]) -> list[UUID]:
    raw_source_ids = workflow_input.get("source_ids")
    if raw_source_ids is None:
        filters = workflow_input.get("filters")
        if isinstance(filters, dict):
            raw_source_ids = filters.get("source_ids")
    if not isinstance(raw_source_ids, list):
        return []
    return [_uuid(str(item), "source_id") for item in raw_source_ids if item]


async def _latest_revision_ids(session_factory: SessionFactory, workspace_id: UUID, source_ids: list[UUID]) -> list[UUID]:
    from deerflow.knowledge.models import DocumentRevision

    async with KnowledgeUnitOfWork(session_factory) as uow:
        assert uow.session is not None
        stmt = select(DocumentRevision).where(DocumentRevision.workspace_id == workspace_id).order_by(DocumentRevision.source_id, DocumentRevision.revision_number.desc())
        if source_ids:
            stmt = stmt.where(DocumentRevision.source_id.in_(source_ids))
        revision_pairs = [(revision.source_id, revision.id) for revision in (await uow.session.execute(stmt)).scalars()]
    latest_by_source: dict[UUID, UUID] = {}
    for source_id, revision_id in revision_pairs:
        latest_by_source.setdefault(source_id, revision_id)
    return list(latest_by_source.values())[:20]


async def _workflow_type_for_run(session_factory: SessionFactory, workspace_id: UUID, workflow_run_id: UUID) -> str:
    async with KnowledgeUnitOfWork(session_factory) as uow:
        run = await uow.workflow_runs.get_by_id(workspace_id, workflow_run_id)
        if run is None:
            raise ValueError("WorkflowRun does not belong to workspace")
        return str(run.workflow_type)


async def _workflow_evidence_items(session_factory: SessionFactory, workspace_id: UUID, revision_ids: list[UUID]) -> list[dict[str, Any]]:
    if not revision_ids:
        return []
    from deerflow.knowledge.models import ClaimEvidenceLink, DocumentRevision, EvidenceSpan, Source

    async with KnowledgeUnitOfWork(session_factory) as uow:
        assert uow.session is not None
        rows = (
            await uow.session.execute(
                select(Claim, EvidenceSpan, Chunk, DocumentRevision, Source)
                .join(ClaimEvidenceLink, (ClaimEvidenceLink.claim_id == Claim.id) & (ClaimEvidenceLink.workspace_id == Claim.workspace_id))
                .join(EvidenceSpan, (EvidenceSpan.id == ClaimEvidenceLink.evidence_span_id) & (EvidenceSpan.workspace_id == ClaimEvidenceLink.workspace_id))
                .join(Chunk, (Chunk.id == EvidenceSpan.chunk_id) & (Chunk.workspace_id == EvidenceSpan.workspace_id))
                .join(DocumentRevision, (DocumentRevision.id == Chunk.revision_id) & (DocumentRevision.workspace_id == Chunk.workspace_id))
                .join(Source, (Source.id == DocumentRevision.source_id) & (Source.workspace_id == DocumentRevision.workspace_id))
                .where(
                    Claim.workspace_id == workspace_id,
                    DocumentRevision.id.in_(revision_ids),
                )
                .order_by(Source.title, DocumentRevision.revision_number.desc(), Chunk.chunk_index, EvidenceSpan.created_at)
                .limit(12)
            )
        ).all()
        return [
            {
                "claim_id": str(claim.id),
                "claim_text": claim.claim_text,
                "evidence_span_id": str(span.id),
                "revision_id": str(revision.id),
                "revision_number": revision.revision_number,
                "chunk_id": str(chunk.id),
                "source_id": str(source.id),
                "source_title": source.title or source.canonical_uri,
                "source_uri": source.canonical_uri,
                "quoted_text": span.quoted_text,
                "start_offset": span.start_offset,
                "end_offset": span.end_offset,
                "section_path": _jsonable(chunk.section_path or []),
            }
            for claim, span, chunk, revision, source in rows
        ]


def _workflow_sections(workflow_type: str, workflow_input: dict[str, Any], evidence_items: list[dict[str, Any]]) -> dict[str, str]:
    topic = workflow_input.get("decision") or workflow_input.get("project") or workflow_input.get("topic") or workflow_input.get("meeting") or workflow_input.get("reading_set") or "Knowledge workflow"
    evidence_lines = [f"- {item['claim_text']} [{item['source_title']} rev {item['revision_number']}]" for item in evidence_items] or ["- No structured evidence was available."]
    if workflow_type == WorkflowType.PROJECT_CONTEXT_PACK.value:
        return {
            "Executive Summary": f"Context pack for {topic}.",
            "Decision Context": f"The project context is grounded in {len(evidence_items)} evidence item(s).",
            "Evidence": "\n".join(evidence_lines),
            "Risks": "Review stale or conflicting evidence before using this pack for planning.",
            "Recommendation": "Use the linked citations as the current project context baseline.",
            "Open Questions": "Confirm whether additional project sources should be ingested.",
            "Adoption / Next Steps": "Share the context pack with collaborators and refresh it after source updates.",
            "References / Citations": "\n".join(f"- {item['source_title']} / revision {item['revision_number']}" for item in evidence_items) or "- None",
        }
    return {
        "Executive Summary": f"Decision memo for {topic}.",
        "Decision Context": f"The memo is based on {len(evidence_items)} evidence item(s) from the knowledge base.",
        "Options / Alternatives": "\n".join(str(item) for item in workflow_input.get("options") or ["Proceed with cited evidence", "Wait for more evidence"]),
        "Evidence": "\n".join(evidence_lines),
        "Risks": "Evidence may become stale when source revisions change.",
        "Recommendation": "Proceed only after reviewing the cited evidence and open questions.",
        "Open Questions": "Check unresolved or insufficient evidence before final approval.",
        "Adoption / Next Steps": "Record the decision, monitor source changes, and regenerate stale artifacts when needed.",
        "References / Citations": "\n".join(f"- {item['source_title']} / revision {item['revision_number']}" for item in evidence_items) or "- None",
    }


async def _persist_workflow_artifact_from_state(
    session_factory: SessionFactory,
    context: TrustedKnowledgeContext,
    workflow_run_id: UUID,
    *,
    idempotency_key: str | None = None,
) -> ArtifactWriteResult:
    async with KnowledgeUnitOfWork(session_factory) as uow:
        assert uow.session is not None
        run = await uow.workflow_runs.get_by_id(context.workspace_id, workflow_run_id)
        if run is None:
            raise ValueError("WorkflowRun does not belong to workspace")
        steps = await uow.workflow_steps.list_for_workflow(context.workspace_id, workflow_run_id)
        workflow_type = str(run.workflow_type)
        workflow_input = dict(run.input or {})
        outputs = {step.step_key: dict(step.output_payload or {}) for step in steps if step.status == WorkflowStatus.SUCCEEDED}
    analysis = outputs.get("analyze_evidence") or outputs.get("review_knowledge_update") or {}
    retrieve = outputs.get("retrieve_evidence") or {}
    artifact_type = _artifact_type_for_workflow(workflow_type)
    title = _artifact_title_for_workflow(workflow_type, workflow_input)
    sections = dict(analysis.get("sections") or {})
    if not sections:
        sections = _workflow_sections(workflow_type, workflow_input, list(retrieve.get("evidence_items") or []))
    json_payload = {
        "workflow_run_id": str(workflow_run_id),
        "workflow_type": workflow_type,
        "title": title,
        "sections": sections,
        "evidence_items": retrieve.get("evidence_items") or [],
        "action_draft": (outputs.get("create_action_draft") or {}).get("action_draft"),
    }
    markdown = _artifact_markdown(title, sections, list(retrieve.get("evidence_items") or []))
    return await WorkflowArtifactService(session_factory).persist_artifact(
        ArtifactWriteRequest(
            workspace_id=context.workspace_id,
            workflow_run_id=workflow_run_id,
            user_id=context.user_id,
            thread_id=context.thread_id,
            artifact_type=artifact_type,
            title=title,
            json_payload=json_payload,
            markdown=markdown,
            evidence_span_ids=tuple(UUID(item) for item in retrieve.get("evidence_span_ids") or []),
            claim_ids=tuple(UUID(item) for item in retrieve.get("claim_ids") or []),
            revision_ids=tuple(UUID(item) for item in retrieve.get("revision_ids") or []),
            usage_type="direct_evidence",
            idempotency_key=idempotency_key or f"{workflow_run_id}:artifact:{artifact_type}",
        )
    )


def _artifact_type_for_workflow(workflow_type: str) -> str:
    if workflow_type == WorkflowType.PROJECT_CONTEXT_PACK.value:
        return "project_context_pack"
    if workflow_type == WorkflowType.KNOWLEDGE_UPDATE_REVIEW.value:
        return "knowledge_update_review"
    if workflow_type == WorkflowType.KNOWLEDGE_TO_ACTION.value:
        return "action_draft"
    if workflow_type == WorkflowType.TOPIC_DOSSIER.value:
        return "topic_dossier"
    if workflow_type == WorkflowType.READING_SYNTHESIS.value:
        return "reading_synthesis"
    if workflow_type == WorkflowType.MEETING_PREPARATION.value:
        return "meeting_preparation"
    return "decision_memo"


def _artifact_title_for_workflow(workflow_type: str, workflow_input: dict[str, Any]) -> str:
    value = workflow_input.get("decision") or workflow_input.get("project") or workflow_input.get("topic") or workflow_input.get("meeting") or workflow_input.get("objective") or "Knowledge artifact"
    if workflow_type == WorkflowType.PROJECT_CONTEXT_PACK.value:
        return f"Project Context Pack: {value}"
    if workflow_type == WorkflowType.KNOWLEDGE_TO_ACTION.value:
        return f"Action Draft: {value}"
    if workflow_type == WorkflowType.TOPIC_DOSSIER.value:
        return f"Topic Dossier: {value}"
    return f"Decision Memo: {value}" if workflow_type == WorkflowType.DECISION_MEMO.value else str(value)


def _artifact_markdown(title: str, sections: dict[str, str], evidence_items: list[dict[str, Any]]) -> str:
    lines = [f"# {title}", ""]
    for heading, body in sections.items():
        lines.extend([f"## {heading}", str(body).strip() or "Not available.", ""])
    lines.extend(["## References / Citations"])
    if evidence_items:
        for item in evidence_items:
            lines.append(f"- {item['source_title']} revision {item['revision_number']}: {item['quoted_text']}")
    else:
        lines.append("- No citations available.")
    lines.append("")
    return "\n".join(lines)


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


async def _artifact_evidence_link_payloads(session: AsyncSession, workspace_id: UUID, artifact_id: UUID) -> list[dict[str, Any]]:
    from deerflow.knowledge.models import ArtifactEvidenceLink, DocumentRevision, EvidenceSpan, Source

    rows = (
        await session.execute(
            select(ArtifactEvidenceLink, Claim, EvidenceSpan, Chunk, DocumentRevision, Source)
            .outerjoin(Claim, (Claim.id == ArtifactEvidenceLink.claim_id) & (Claim.workspace_id == ArtifactEvidenceLink.workspace_id))
            .outerjoin(EvidenceSpan, (EvidenceSpan.id == ArtifactEvidenceLink.evidence_span_id) & (EvidenceSpan.workspace_id == ArtifactEvidenceLink.workspace_id))
            .outerjoin(Chunk, (Chunk.id == EvidenceSpan.chunk_id) & (Chunk.workspace_id == EvidenceSpan.workspace_id))
            .outerjoin(DocumentRevision, (DocumentRevision.id == Chunk.revision_id) & (DocumentRevision.workspace_id == Chunk.workspace_id))
            .outerjoin(Source, (Source.id == DocumentRevision.source_id) & (Source.workspace_id == DocumentRevision.workspace_id))
            .where(
                ArtifactEvidenceLink.workspace_id == workspace_id,
                ArtifactEvidenceLink.artifact_id == artifact_id,
            )
            .order_by(ArtifactEvidenceLink.created_at, ArtifactEvidenceLink.id)
        )
    ).all()
    return [
        {
            "artifact_evidence_link_id": str(link.id),
            "artifact_id": str(link.artifact_id),
            "usage_type": link.usage_type,
            "claim_id": str(link.claim_id) if link.claim_id else None,
            "claim_text": claim.claim_text if claim else None,
            "evidence_span_id": str(link.evidence_span_id) if link.evidence_span_id else None,
            "revision_id": str(link.revision_id or (revision.id if revision else "")) or None,
            "chunk_id": str(chunk.id) if chunk else None,
            "source_id": str(source.id) if source else None,
            "source_title": (source.title or source.canonical_uri) if source else None,
            "source_uri": source.canonical_uri if source else None,
            "quoted_text": span.quoted_text if span else None,
            "start_offset": span.start_offset if span else None,
            "end_offset": span.end_offset if span else None,
            "page_number": span.page_number if span else None,
            "section_path": _jsonable(chunk.section_path or []) if chunk else [],
            "created_at": link.created_at.astimezone(UTC).isoformat(),
        }
        for link, claim, span, chunk, revision, source in rows
    ]


def _read_artifact_markdown(context: TrustedKnowledgeContext, metadata: dict[str, Any]) -> str:
    markdown_path = metadata.get("markdown_storage_path")
    if not isinstance(markdown_path, str) or not markdown_path:
        return ""
    try:
        path = get_paths().resolve_virtual_path(context.thread_id, markdown_path, user_id=context.user_id)
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


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
