from __future__ import annotations

from uuid import UUID

from deerflow.knowledge.models import ActionExecution, ApprovalRequest, WorkflowRun, WorkflowStepRun
from deerflow.knowledge.repositories.base import WorkspaceRepository


class WorkflowRunRepository(WorkspaceRepository[WorkflowRun]):
    model = WorkflowRun

    async def list_by_status(self, workspace_id: UUID, status: str) -> list[WorkflowRun]:
        return await self._all(self._workspace_stmt(workspace_id).where(WorkflowRun.status == status))

    async def get_by_idempotency_key(self, workspace_id: UUID, workflow_type: str, idempotency_key: str) -> WorkflowRun | None:
        stmt = self._workspace_stmt(workspace_id).where(WorkflowRun.workflow_type == workflow_type, WorkflowRun.idempotency_key == idempotency_key)
        return await self._first(stmt)


class WorkflowStepRunRepository(WorkspaceRepository[WorkflowStepRun]):
    model = WorkflowStepRun

    async def list_for_workflow(self, workspace_id: UUID, workflow_run_id: UUID) -> list[WorkflowStepRun]:
        return await self._all(self._workspace_stmt(workspace_id).where(WorkflowStepRun.workflow_run_id == workflow_run_id).order_by(WorkflowStepRun.sequence))

    async def get_by_key(self, workspace_id: UUID, workflow_run_id: UUID, step_key: str) -> WorkflowStepRun | None:
        stmt = self._workspace_stmt(workspace_id).where(WorkflowStepRun.workflow_run_id == workflow_run_id, WorkflowStepRun.step_key == step_key)
        return await self._first(stmt)


class ApprovalRequestRepository(WorkspaceRepository[ApprovalRequest]):
    model = ApprovalRequest

    async def list_for_workflow(self, workspace_id: UUID, workflow_run_id: UUID) -> list[ApprovalRequest]:
        return await self._all(self._workspace_stmt(workspace_id).where(ApprovalRequest.workflow_run_id == workflow_run_id))


class ActionExecutionRepository(WorkspaceRepository[ActionExecution]):
    model = ActionExecution

    async def get_by_idempotency_key(self, workspace_id: UUID, connector_type: str, idempotency_key: str) -> ActionExecution | None:
        stmt = self._workspace_stmt(workspace_id).where(ActionExecution.connector_type == connector_type, ActionExecution.idempotency_key == idempotency_key)
        return await self._first(stmt)
