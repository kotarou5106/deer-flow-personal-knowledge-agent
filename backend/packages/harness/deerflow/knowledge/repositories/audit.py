from __future__ import annotations

from uuid import UUID

from deerflow.knowledge.models import AuditLog
from deerflow.knowledge.repositories.base import WorkspaceRepository


class AuditLogRepository(WorkspaceRepository[AuditLog]):
    model = AuditLog

    async def list_for_target(self, workspace_id: UUID, target_type: str, target_id: str) -> list[AuditLog]:
        stmt = self._workspace_stmt(workspace_id).where(AuditLog.target_type == target_type, AuditLog.target_id == target_id)
        return await self._all(stmt)
