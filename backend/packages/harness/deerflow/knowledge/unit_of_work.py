from __future__ import annotations

from types import TracebackType
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from deerflow.knowledge.repositories import (
    ActionExecutionRepository,
    ApprovalRequestRepository,
    ArtifactEvidenceLinkRepository,
    ArtifactRepository,
    AuditLogRepository,
    ChunkRepository,
    ClaimRepository,
    CollectionRepository,
    ConflictGroupRepository,
    EntityAliasRepository,
    EntityRepository,
    EvidenceSpanRepository,
    ExtractionRunRepository,
    RelationRepository,
    RevisionRepository,
    SnapshotRepository,
    SourceRepository,
    WorkflowRunRepository,
    WorkflowStepRunRepository,
)


class SessionFactory(Protocol):
    def __call__(self) -> AsyncSession: ...


class KnowledgeUnitOfWork:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory
        self.session: AsyncSession | None = None
        self._committed = False

    async def __aenter__(self) -> KnowledgeUnitOfWork:
        self.session = self._session_factory()
        self.sources = SourceRepository(self.session)
        self.snapshots = SnapshotRepository(self.session)
        self.revisions = RevisionRepository(self.session)
        self.chunks = ChunkRepository(self.session)
        self.entities = EntityRepository(self.session)
        self.entity_aliases = EntityAliasRepository(self.session)
        self.claims = ClaimRepository(self.session)
        self.evidence_spans = EvidenceSpanRepository(self.session)
        self.relations = RelationRepository(self.session)
        self.extraction_runs = ExtractionRunRepository(self.session)
        self.collections = CollectionRepository(self.session)
        self.conflict_groups = ConflictGroupRepository(self.session)
        self.artifacts = ArtifactRepository(self.session)
        self.artifact_evidence_links = ArtifactEvidenceLinkRepository(self.session)
        self.workflow_runs = WorkflowRunRepository(self.session)
        self.workflow_steps = WorkflowStepRunRepository(self.session)
        self.approval_requests = ApprovalRequestRepository(self.session)
        self.action_executions = ActionExecutionRepository(self.session)
        self.audit_logs = AuditLogRepository(self.session)
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None) -> None:
        if self.session is None:
            return
        try:
            if not self._committed:
                await self.session.rollback()
        finally:
            await self.session.close()

    async def commit(self) -> None:
        if self.session is None:
            raise RuntimeError("KnowledgeUnitOfWork is not entered")
        await self.session.commit()
        self._committed = True

    async def rollback(self) -> None:
        if self.session is None:
            raise RuntimeError("KnowledgeUnitOfWork is not entered")
        await self.session.rollback()
        self._committed = False


def knowledge_uow_factory(session_factory: SessionFactory):
    return KnowledgeUnitOfWork(session_factory)
