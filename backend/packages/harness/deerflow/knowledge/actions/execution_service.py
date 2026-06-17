from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import update

from deerflow.knowledge.actions.adapter_registry import ActionAdapterRegistry
from deerflow.knowledge.actions.audit_service import ActionAuditService
from deerflow.knowledge.actions.policies import connector_type_for
from deerflow.knowledge.actions.schemas import ExecutionResult, action_payload_hash, validate_action_draft
from deerflow.knowledge.actions.state_machine import assert_approval_transition_allowed
from deerflow.knowledge.enums import ActionExecutionStatus, ApprovalStatus, WorkflowStatus
from deerflow.knowledge.models import ActionExecution, ApprovalRequest
from deerflow.knowledge.unit_of_work import KnowledgeUnitOfWork, SessionFactory


class ActionExecutionService:
    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        adapters: ActionAdapterRegistry,
        audit_service: ActionAuditService | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._adapters = adapters
        self._audit = audit_service or ActionAuditService(session_factory)

    async def execute(self, *, workspace_id: UUID, approval_request_id: UUID) -> ExecutionResult:
        prepared = await self._prepare_execution(workspace_id, approval_request_id)
        if prepared[0] is None:
            return prepared[1]
        execution_id, action, connector_type, idempotency_key = prepared[0]
        adapter = self._adapters.get(connector_type)

        try:
            adapter_result = await adapter.execute(action, idempotency_key)
        except TimeoutError as exc:
            return await self._mark_reconciliation(workspace_id, approval_request_id, execution_id, str(exc))
        except Exception as exc:
            return await self._mark_failed(workspace_id, approval_request_id, execution_id, str(exc))

        if adapter_result.requires_reconciliation:
            return await self._mark_reconciliation(workspace_id, approval_request_id, execution_id, adapter_result.error_message or "adapter result is unknown")
        if not adapter_result.succeeded:
            return await self._mark_failed(workspace_id, approval_request_id, execution_id, adapter_result.error_message or "adapter failed")
        return await self._mark_succeeded(workspace_id, approval_request_id, execution_id, adapter_result.external_reference, adapter_result.result_payload)

    async def _prepare_execution(self, workspace_id: UUID, approval_request_id: UUID):
        async with KnowledgeUnitOfWork(self._session_factory) as uow:
            assert uow.session is not None
            approval = await uow.approval_requests.get_by_id(workspace_id, approval_request_id)
            if approval is None:
                raise ValueError("ApprovalRequest does not belong to workspace")
            existing = await uow.action_executions.get_for_approval(workspace_id, approval_request_id)
            if existing is not None:
                return None, ExecutionResult(approval_request_id, existing.id, existing.status, False, existing.external_reference, existing.error_message, existing.requires_reconciliation)
            if approval.status != ApprovalStatus.APPROVED:
                raise ValueError("ApprovalRequest is not approved")

            action = validate_action_draft(approval.action_payload)
            if action_payload_hash(action) != approval.action_payload_hash:
                approval.status = ApprovalStatus.FAILED
                approval.decision_reason = "Approved action payload changed before execution"
                await uow.commit()
                raise ValueError("Approved action payload changed; request must be reapproved")
            workflow = await uow.workflow_runs.get_by_id(workspace_id, approval.workflow_run_id)
            if workflow is None:
                raise ValueError("WorkflowRun does not belong to workspace")
            connector_type = connector_type_for(action)
            idempotency_key = f"approval:{approval.id}:{approval.action_payload_hash}"
            if connector_type not in self._adapters.names:
                raise ValueError(f"Missing action adapter: {connector_type}")

            result = await uow.session.execute(
                update(ApprovalRequest)
                .where(
                    ApprovalRequest.workspace_id == workspace_id,
                    ApprovalRequest.id == approval_request_id,
                    ApprovalRequest.status == ApprovalStatus.APPROVED,
                    ApprovalRequest.action_payload_hash == approval.action_payload_hash,
                )
                .values(status=ApprovalStatus.EXECUTING)
            )
            if result.rowcount != 1:
                await uow.rollback()
                existing_after_race = await uow.action_executions.get_for_approval(workspace_id, approval_request_id)
                if existing_after_race is not None:
                    return None, ExecutionResult(
                        approval_request_id,
                        existing_after_race.id,
                        existing_after_race.status,
                        False,
                        existing_after_race.external_reference,
                        existing_after_race.error_message,
                        existing_after_race.requires_reconciliation,
                    )
                raise ValueError("ApprovalRequest could not acquire execution lock")

            execution = ActionExecution(
                id=uuid4(),
                workspace_id=workspace_id,
                approval_request_id=approval_request_id,
                action_type=action.action_type.value,
                connector_type=connector_type,
                idempotency_key=idempotency_key,
                action_payload_hash=approval.action_payload_hash,
                request_payload=approval.action_payload,
                status=ActionExecutionStatus.RUNNING,
                started_at=datetime.now(UTC),
            )
            uow.session.add(execution)
            await uow.session.flush()
            await uow.commit()
        await self._audit.append(
            workspace_id=workspace_id,
            actor_id=None,
            event_type="execution_started",
            target_type="action_execution",
            target_id=str(execution.id),
            payload={"approval_request_id": str(approval_request_id), "action_execution_id": str(execution.id), "connector_type": connector_type},
        )
        return (execution.id, action, connector_type, idempotency_key), None

    async def _mark_succeeded(self, workspace_id: UUID, approval_request_id: UUID, execution_id: UUID, external_reference: str | None, result_payload: dict) -> ExecutionResult:
        async with KnowledgeUnitOfWork(self._session_factory) as uow:
            execution = await uow.action_executions.get_by_id(workspace_id, execution_id)
            approval = await uow.approval_requests.get_by_id(workspace_id, approval_request_id)
            if execution is None or approval is None:
                raise ValueError("Execution does not belong to workspace")
            execution.status = ActionExecutionStatus.SUCCEEDED
            execution.external_reference = external_reference
            execution.result_payload = result_payload
            execution.executed_at = datetime.now(UTC)
            assert_approval_transition_allowed(approval.status, ApprovalStatus.SUCCEEDED)
            approval.status = ApprovalStatus.SUCCEEDED
            workflow = await uow.workflow_runs.get_by_id(workspace_id, approval.workflow_run_id)
            if workflow is not None and workflow.status == WorkflowStatus.REQUIRES_APPROVAL:
                workflow.status = WorkflowStatus.COMPLETED
                workflow.current_step = None
                workflow.completed_at = datetime.now(UTC)
            await uow.commit()
        await self._audit.append(
            workspace_id=workspace_id,
            actor_id=None,
            event_type="execution_succeeded",
            target_type="action_execution",
            target_id=str(execution_id),
            payload={"approval_request_id": str(approval_request_id), "external_reference": external_reference},
        )
        return ExecutionResult(approval_request_id, execution_id, ActionExecutionStatus.SUCCEEDED, True, external_reference)

    async def _mark_failed(self, workspace_id: UUID, approval_request_id: UUID, execution_id: UUID, error: str) -> ExecutionResult:
        async with KnowledgeUnitOfWork(self._session_factory) as uow:
            execution = await uow.action_executions.get_by_id(workspace_id, execution_id)
            approval = await uow.approval_requests.get_by_id(workspace_id, approval_request_id)
            if execution is None or approval is None:
                raise ValueError("Execution does not belong to workspace")
            execution.status = ActionExecutionStatus.FAILED
            execution.error_message = error[:2000]
            execution.executed_at = datetime.now(UTC)
            assert_approval_transition_allowed(approval.status, ApprovalStatus.FAILED)
            approval.status = ApprovalStatus.FAILED
            approval.decision_reason = execution.error_message
            workflow = await uow.workflow_runs.get_by_id(workspace_id, approval.workflow_run_id)
            if workflow is not None:
                workflow.status = WorkflowStatus.FAILED
                workflow.error = execution.error_message
            await uow.commit()
        await self._audit.append(
            workspace_id=workspace_id,
            actor_id=None,
            event_type="execution_failed",
            target_type="action_execution",
            target_id=str(execution_id),
            payload={"approval_request_id": str(approval_request_id), "error": error[:500]},
        )
        return ExecutionResult(approval_request_id, execution_id, ActionExecutionStatus.FAILED, True, error=error)

    async def _mark_reconciliation(self, workspace_id: UUID, approval_request_id: UUID, execution_id: UUID, error: str) -> ExecutionResult:
        async with KnowledgeUnitOfWork(self._session_factory) as uow:
            execution = await uow.action_executions.get_by_id(workspace_id, execution_id)
            approval = await uow.approval_requests.get_by_id(workspace_id, approval_request_id)
            if execution is None or approval is None:
                raise ValueError("Execution does not belong to workspace")
            execution.status = ActionExecutionStatus.RECONCILIATION_REQUIRED
            execution.error_message = error[:2000]
            execution.requires_reconciliation = True
            execution.executed_at = datetime.now(UTC)
            approval.status = ApprovalStatus.FAILED
            approval.decision_reason = "Execution requires reconciliation"
            workflow = await uow.workflow_runs.get_by_id(workspace_id, approval.workflow_run_id)
            if workflow is not None:
                workflow.status = WorkflowStatus.FAILED
                workflow.error = "Execution requires reconciliation"
            await uow.commit()
        await self._audit.append(
            workspace_id=workspace_id,
            actor_id=None,
            event_type="execution_reconciliation_required",
            target_type="action_execution",
            target_id=str(execution_id),
            payload={"approval_request_id": str(approval_request_id), "error": error[:500]},
        )
        return ExecutionResult(approval_request_id, execution_id, ActionExecutionStatus.RECONCILIATION_REQUIRED, True, error=error, requires_reconciliation=True)
