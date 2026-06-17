from __future__ import annotations

import json
import re
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

from deerflow.config.paths import VIRTUAL_PATH_PREFIX, Paths, get_paths
from deerflow.knowledge.enums import ArtifactStalenessStatus, ArtifactValidationStatus
from deerflow.knowledge.models import Artifact, ArtifactEvidenceLink, WorkflowArtifact
from deerflow.knowledge.unit_of_work import KnowledgeUnitOfWork, SessionFactory
from deerflow.knowledge.workflows.schemas import ArtifactWriteRequest, ArtifactWriteResult


class WorkflowArtifactService:
    def __init__(self, session_factory: SessionFactory, *, paths: Paths | None = None) -> None:
        self._session_factory = session_factory
        self._paths = paths or get_paths()

    async def persist_artifact(self, request: ArtifactWriteRequest) -> ArtifactWriteResult:
        existing = await self._find_existing(request)
        if existing is not None:
            return existing

        json_path, markdown_path = self._paths_for(request)
        written_paths: list[Path] = []
        try:
            json_path.parent.mkdir(parents=True, exist_ok=True)
            json_path.write_text(json.dumps(request.json_payload, ensure_ascii=False, indent=2), encoding="utf-8")
            written_paths.append(json_path)
            markdown_path.write_text(request.markdown, encoding="utf-8")
            written_paths.append(markdown_path)

            async with KnowledgeUnitOfWork(self._session_factory) as uow:
                assert uow.session is not None
                artifact = Artifact(
                    workspace_id=request.workspace_id,
                    artifact_type=request.artifact_type,
                    title=request.title,
                    storage_path=_virtual_path(json_path, request.thread_id, request.user_id, self._paths),
                    validation_status=ArtifactValidationStatus.VALID,
                    staleness_status=ArtifactStalenessStatus.FRESH,
                    metadata_json={
                        "workflow_run_id": str(request.workflow_run_id),
                        "idempotency_key": request.idempotency_key,
                        "markdown_storage_path": _virtual_path(markdown_path, request.thread_id, request.user_id, self._paths),
                    },
                )
                uow.session.add(artifact)
                await uow.session.flush()
                uow.session.add(WorkflowArtifact(workspace_id=request.workspace_id, workflow_run_id=request.workflow_run_id, artifact_id=artifact.id))
                link_count = await _add_evidence_links(uow.session, artifact.id, request)
                await uow.commit()
                written_paths.clear()
                return ArtifactWriteResult(artifact.id, artifact.storage_path, artifact.metadata_json["markdown_storage_path"], link_count)
        except Exception:
            for path in written_paths:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
            raise

    async def _find_existing(self, request: ArtifactWriteRequest) -> ArtifactWriteResult | None:
        if not request.idempotency_key:
            return None
        async with KnowledgeUnitOfWork(self._session_factory) as uow:
            assert uow.session is not None
            artifact = (
                await uow.session.execute(
                    select(Artifact)
                    .join(WorkflowArtifact, (WorkflowArtifact.artifact_id == Artifact.id) & (WorkflowArtifact.workspace_id == Artifact.workspace_id))
                    .where(
                        Artifact.workspace_id == request.workspace_id,
                        WorkflowArtifact.workflow_run_id == request.workflow_run_id,
                        Artifact.metadata_json["idempotency_key"].as_string() == request.idempotency_key,
                    )
                    .limit(1)
                )
            ).scalar_one_or_none()
            if artifact is None:
                return None
            link_count = len(
                (
                    await uow.session.execute(
                        select(ArtifactEvidenceLink).where(
                            ArtifactEvidenceLink.workspace_id == request.workspace_id,
                            ArtifactEvidenceLink.artifact_id == artifact.id,
                        )
                    )
                )
                .scalars()
                .all()
            )
            return ArtifactWriteResult(
                artifact.id,
                artifact.storage_path,
                str((artifact.metadata_json or {}).get("markdown_storage_path") or ""),
                link_count,
            )

    def _paths_for(self, request: ArtifactWriteRequest) -> tuple[Path, Path]:
        safe_name = _safe_file_stem(request.idempotency_key or request.title)
        base_dir = self._paths.sandbox_outputs_dir(request.thread_id, user_id=request.user_id) / "knowledge-workflows" / str(request.workflow_run_id)
        return base_dir / f"{safe_name}.json", base_dir / f"{safe_name}.md"


async def _add_evidence_links(session, artifact_id: UUID, request: ArtifactWriteRequest) -> int:
    count = 0
    for evidence_span_id in request.evidence_span_ids or (None,):
        for claim_id in request.claim_ids or (None,):
            for revision_id in request.revision_ids or (None,):
                exists = (
                    await session.execute(
                        select(ArtifactEvidenceLink.id)
                        .where(
                            ArtifactEvidenceLink.workspace_id == request.workspace_id,
                            ArtifactEvidenceLink.artifact_id == artifact_id,
                            ArtifactEvidenceLink.evidence_span_id.is_(None) if evidence_span_id is None else ArtifactEvidenceLink.evidence_span_id == evidence_span_id,
                            ArtifactEvidenceLink.claim_id.is_(None) if claim_id is None else ArtifactEvidenceLink.claim_id == claim_id,
                            ArtifactEvidenceLink.revision_id.is_(None) if revision_id is None else ArtifactEvidenceLink.revision_id == revision_id,
                            ArtifactEvidenceLink.usage_type == request.usage_type,
                        )
                        .limit(1)
                    )
                ).scalar_one_or_none()
                if exists is not None:
                    continue
                session.add(
                    ArtifactEvidenceLink(
                        workspace_id=request.workspace_id,
                        artifact_id=artifact_id,
                        evidence_span_id=evidence_span_id,
                        claim_id=claim_id,
                        revision_id=revision_id,
                        usage_type=request.usage_type,
                    )
                )
                count += 1
    await session.flush()
    return count


def _safe_file_stem(value: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-._")
    return stem[:96] or "artifact"


def _virtual_path(path: Path, thread_id: str, user_id: str, paths: Paths) -> str:
    base = paths.sandbox_user_data_dir(thread_id, user_id=user_id).resolve()
    try:
        relative = path.resolve().relative_to(base)
    except ValueError:
        raise ValueError("Artifact path escaped DeerFlow user-scoped storage") from None
    return f"{VIRTUAL_PATH_PREFIX}/{relative.as_posix()}"
