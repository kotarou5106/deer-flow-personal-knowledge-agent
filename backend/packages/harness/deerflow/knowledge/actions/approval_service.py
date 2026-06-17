from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from deerflow.knowledge.actions.audit_service import ActionAuditService
from deerflow.knowledge.actions.schemas import ApprovalResult, action_payload_for_storage, validate_action_draft
from deerflow.knowledge.actions.state_machine import assert_approval_transition_allowed
from deerflow.knowledge.enums import ApprovalStatus, WorkflowStatus
from deerflow.knowledge.models import ApprovalRequest
from deerflow.knowledge.unit_of_work import KnowledgeUnitOfWork, SessionFactory


class ApprovalService:
    def __init__(self, session_factory: SessionFactory, *, audit_service: ActionAuditService | None = None) -> None:
        self._session_factory = session_factory
        self._audit = audit_service or ActionAuditService(session_factory)

    async def request_approval(self, *, workspace_id: UUID, action_draft, actor_id: str | None = None) -> ApprovalResult:
        action = validate_action_draft(action_draft)
        async with KnowledgeUnitOfWork(self._session_factory) as uow:
            assert uow.session is not None
            workflow = await uow.workflow_runs.get_by_id(workspace_id, action.source_workflow_run_id)
            if workflow is None:
                raise ValueError("WorkflowRun does not belong to workspace")
            if workflow.status != WorkflowStatus.REQUIRES_APPROVAL:
                raise ValueError("WorkflowRun is not waiting for approval")
            if action.source_step_run_id is not None:
                step = await uow.workflow_steps.get_by_id(workspace_id, action.source_step_run_id)
                if step is None or step.workflow_run_id != workflow.id:
                    raise ValueError("WorkflowStepRun does not belong to workflow workspace")
            approval = ApprovalRequest(
                workspace_id=workspace_id,
                workflow_run_id=workflow.id,
                source_step_run_id=action.source_step_run_id,
                action_type=action.action_type.value,
                target=action.target,
                action_payload=action_payload_for_storage(action),
                action_payload_hash=action.payload_hash,
                action_preview=action.preview,
                risk_level=action.risk_level,
                status=ApprovalStatus.AWAITING_APPROVAL,
                requested_by=actor_id,
            )
            uow.session.add(approval)
            await uow.session.flush()
            await uow.commit()
        await self._audit.append(
            workspace_id=workspace_id,
            actor_id=actor_id,
            event_type="approval_requested",
            target_type="approval_request",
            target_id=str(approval.id),
            payload={"approval_request_id": str(approval.id), "workflow_run_id": str(action.source_workflow_run_id), "action_type": action.action_type.value},
        )
        return ApprovalResult(approval.id, approval.status, approval.action_payload_hash)

    async def approve(self, *, workspace_id: UUID, approval_request_id: UUID, actor_id: str, reason: str | None = None) -> ApprovalResult:
        return await self._decide(workspace_id=workspace_id, approval_request_id=approval_request_id, actor_id=actor_id, target=ApprovalStatus.APPROVED, reason=reason, event_type="approval_approved")

    async def reject(self, *, workspace_id: UUID, approval_request_id: UUID, actor_id: str, reason: str | None = None) -> ApprovalResult:
        return await self._decide(workspace_id=workspace_id, approval_request_id=approval_request_id, actor_id=actor_id, target=ApprovalStatus.REJECTED, reason=reason, event_type="approval_rejected")

    async def cancel(self, *, workspace_id: UUID, approval_request_id: UUID, actor_id: str, reason: str | None = None) -> ApprovalResult:
        return await self._decide(workspace_id=workspace_id, approval_request_id=approval_request_id, actor_id=actor_id, target=ApprovalStatus.CANCELLED, reason=reason, event_type="approval_cancelled")

    async def _decide(
        self,
        *,
        workspace_id: UUID,
        approval_request_id: UUID,
        actor_id: str,
        target: ApprovalStatus,
        reason: str | None,
        event_type: str,
    ) -> ApprovalResult:
        async with KnowledgeUnitOfWork(self._session_factory) as uow:
            approval = await uow.approval_requests.get_by_id(workspace_id, approval_request_id)
            if approval is None:
                raise ValueError("ApprovalRequest does not belong to workspace")
            assert_approval_transition_allowed(approval.status, target)
            approval.status = target
            approval.decided_by = actor_id
            approval.decided_at = datetime.now(UTC)
            approval.decision_reason = reason
            workflow = await uow.workflow_runs.get_by_id(workspace_id, approval.workflow_run_id)
            if workflow is not None and target in {ApprovalStatus.REJECTED, ApprovalStatus.CANCELLED}:
                workflow.error = f"Approval {target.value}: {reason or ''}".strip()
            await uow.commit()
        await self._audit.append(
            workspace_id=workspace_id,
            actor_id=actor_id,
            event_type=event_type,
            target_type="approval_request",
            target_id=str(approval_request_id),
            payload={"approval_request_id": str(approval_request_id), "reason": reason},
        )
        return ApprovalResult(approval.id, approval.status, approval.action_payload_hash)
