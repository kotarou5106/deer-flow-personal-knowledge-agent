from __future__ import annotations

from uuid import UUID

from deerflow.knowledge.models import Artifact, ArtifactEvidenceLink
from deerflow.knowledge.repositories.base import WorkspaceRepository


class ArtifactRepository(WorkspaceRepository[Artifact]):
    model = Artifact

    async def list_by_staleness(self, workspace_id: UUID, staleness_status: str) -> list[Artifact]:
        return await self._all(self._workspace_stmt(workspace_id).where(Artifact.staleness_status == staleness_status))


class ArtifactEvidenceLinkRepository(WorkspaceRepository[ArtifactEvidenceLink]):
    model = ArtifactEvidenceLink

    async def list_for_artifact(self, workspace_id: UUID, artifact_id: UUID) -> list[ArtifactEvidenceLink]:
        return await self._all(self._workspace_stmt(workspace_id).where(ArtifactEvidenceLink.artifact_id == artifact_id))
