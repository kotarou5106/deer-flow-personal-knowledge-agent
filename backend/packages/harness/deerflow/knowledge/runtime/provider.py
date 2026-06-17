from __future__ import annotations

import asyncio
import hashlib
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Protocol
from uuid import UUID

from pydantic import SecretStr
from sqlalchemy import func, select

from deerflow.knowledge.config import KnowledgeDatabaseConfig
from deerflow.knowledge.database import KnowledgeDatabase
from deerflow.knowledge.enums import ApprovalStatus, RiskLevel
from deerflow.knowledge.ingestion.models import SourceInput
from deerflow.knowledge.ingestion.pipeline import IngestionPipeline
from deerflow.knowledge.models import ApprovalRequest
from deerflow.knowledge.retrieval.service import RetrievalService
from deerflow.knowledge.runtime.context import TrustedKnowledgeContext
from deerflow.knowledge.unit_of_work import KnowledgeUnitOfWork


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
        raise KnowledgeServiceUnavailableError("Knowledge analysis service is not configured")

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
            revisions = await uow.revisions.list_for_source(context.workspace_id, source_uuid)
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
        raise KnowledgeServiceUnavailableError("Knowledge update service is not configured")

    async def find_conflicts(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]:
        limit = min(int(payload.get("limit") or 50), 100)
        offset = max(int(payload.get("offset") or 0), 0)
        async with KnowledgeUnitOfWork(self._session_factory) as uow:
            rows = await uow.conflict_groups.list_for_workspace(context.workspace_id, limit=limit, offset=offset)
            return {
                "data": [
                    {
                        "conflict_group_id": str(row.id),
                        "status": row.status.value,
                        "summary": row.summary,
                        "created_at": row.created_at.astimezone(UTC).isoformat(),
                    }
                    for row in rows
                ],
                "pagination": {"limit": limit, "offset": offset},
            }

    async def generate_update_report(self, context: TrustedKnowledgeContext, payload: dict[str, Any]) -> dict[str, Any]:
        raise KnowledgeServiceUnavailableError("Knowledge update service is not configured")

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
