from __future__ import annotations

from uuid import UUID

from deerflow.knowledge.models import Claim, Collection, ConflictGroup, Entity, EvidenceSpan, Relation
from deerflow.knowledge.repositories.base import WorkspaceRepository


class EntityRepository(WorkspaceRepository[Entity]):
    model = Entity

    async def list_by_name(self, workspace_id: UUID, canonical_name: str) -> list[Entity]:
        return await self._all(self._workspace_stmt(workspace_id).where(Entity.canonical_name == canonical_name))


class ClaimRepository(WorkspaceRepository[Claim]):
    model = Claim

    async def list_by_status(self, workspace_id: UUID, status: str) -> list[Claim]:
        return await self._all(self._workspace_stmt(workspace_id).where(Claim.status == status))


class EvidenceSpanRepository(WorkspaceRepository[EvidenceSpan]):
    model = EvidenceSpan

    async def list_for_chunk(self, workspace_id: UUID, chunk_id: UUID) -> list[EvidenceSpan]:
        return await self._all(self._workspace_stmt(workspace_id).where(EvidenceSpan.chunk_id == chunk_id))


class RelationRepository(WorkspaceRepository[Relation]):
    model = Relation

    async def list_for_entity(self, workspace_id: UUID, entity_id: UUID) -> list[Relation]:
        stmt = self._workspace_stmt(workspace_id).where((Relation.source_entity_id == entity_id) | (Relation.target_entity_id == entity_id))
        return await self._all(stmt)


class CollectionRepository(WorkspaceRepository[Collection]):
    model = Collection


class ConflictGroupRepository(WorkspaceRepository[ConflictGroup]):
    model = ConflictGroup
