from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select

from deerflow.knowledge.enums import WorkflowStatus
from deerflow.knowledge.models import WorkflowRun, WorkflowStepRun
from deerflow.knowledge.unit_of_work import KnowledgeUnitOfWork, SessionFactory
from deerflow.knowledge.workflows.handlers import HandlerRegistry
from deerflow.knowledge.workflows.registry import WorkflowDefinitionRegistry
from deerflow.knowledge.workflows.schemas import (
    WORKFLOW_ENGINE_NAME,
    WORKFLOW_ENGINE_VERSION,
    StepHandlerContext,
    StepHandlerResult,
    WorkflowRunResult,
    WorkflowType,
)
from deerflow.knowledge.workflows.state_machine import assert_transition_allowed


class WorkflowEngine:
    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        definitions: WorkflowDefinitionRegistry | None = None,
        handlers: HandlerRegistry | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._definitions = definitions or WorkflowDefinitionRegistry()
        self._handlers = handlers or HandlerRegistry()

    async def create(
        self,
        *,
        workspace_id: UUID,
        workflow_type: WorkflowType | str,
        input_payload: dict,
        idempotency_key: str | None = None,
    ) -> WorkflowRunResult:
        definition = self._definitions.get(workflow_type)
        definition.input_schema.validate(input_payload)
        self._definitions.validate_handlers(definition, self._handlers.names)

        async with KnowledgeUnitOfWork(self._session_factory) as uow:
            assert uow.session is not None
            if idempotency_key:
                existing = await uow.workflow_runs.get_by_idempotency_key(workspace_id, definition.workflow_type, idempotency_key)
                if existing is not None:
                    return await _result_for_run(uow.session, existing)

            run = WorkflowRun(
                id=uuid4(),
                workspace_id=workspace_id,
                workflow_type=definition.workflow_type,
                input=input_payload,
                status=WorkflowStatus.READY,
                idempotency_key=idempotency_key,
                metadata_json={
                    "engine_name": WORKFLOW_ENGINE_NAME,
                    "engine_version": WORKFLOW_ENGINE_VERSION,
                    "completion_conditions": list(definition.completion_conditions),
                    "external_action_may_follow": definition.whether_external_action_may_follow,
                },
            )
            uow.session.add(run)
            await uow.session.flush()
            for step in definition.ordered_steps:
                uow.session.add(
                    WorkflowStepRun(
                        workspace_id=workspace_id,
                        workflow_run_id=run.id,
                        step_key=step.step_key,
                        sequence=step.sequence,
                        status=WorkflowStatus.PENDING,
                        input_payload={},
                        output_payload={},
                        attempt=0,
                        idempotency_key=f"{run.id}:{step.step_key}:{step.sequence}",
                    )
                )
            await uow.session.flush()
            await uow.commit()
            return await self._get_result(workspace_id, run.id)

    async def advance(self, *, workspace_id: UUID, workflow_run_id: UUID) -> WorkflowRunResult:
        run, step, previous_outputs = await self._start_next_step(workspace_id, workflow_run_id)
        if step is None:
            return await self._get_result(workspace_id, workflow_run_id)

        try:
            definition = self._definitions.get(run.workflow_type)
            step_definition = next(item for item in definition.ordered_steps if item.step_key == step.step_key)
            handler = self._handlers.get(step_definition.handler_name)
            result = await handler(
                StepHandlerContext(
                    workspace_id=workspace_id,
                    workflow_run_id=workflow_run_id,
                    step_key=step.step_key,
                    input_payload=step.input_payload,
                    previous_outputs=previous_outputs,
                    attempt=step.attempt,
                )
            )
            if not isinstance(result, StepHandlerResult) or not isinstance(result.output_payload, dict):
                raise ValueError("Workflow handler returned an invalid step result")
            return await self._complete_step(workspace_id, workflow_run_id, step.id, result)
        except Exception as exc:
            await self._fail_step(workspace_id, workflow_run_id, step.id, exc)
            return await self._get_result(workspace_id, workflow_run_id)

    async def pause(self, *, workspace_id: UUID, workflow_run_id: UUID) -> WorkflowRunResult:
        async with KnowledgeUnitOfWork(self._session_factory) as uow:
            run = await uow.workflow_runs.get_by_id(workspace_id, workflow_run_id)
            if run is None:
                raise ValueError("WorkflowRun does not belong to workspace")
            assert_transition_allowed(run.status, WorkflowStatus.PAUSED)
            run.status = WorkflowStatus.PAUSED
            await uow.commit()
        return await self._get_result(workspace_id, workflow_run_id)

    async def resume(self, *, workspace_id: UUID, workflow_run_id: UUID) -> WorkflowRunResult:
        async with KnowledgeUnitOfWork(self._session_factory) as uow:
            run = await uow.workflow_runs.get_by_id(workspace_id, workflow_run_id)
            if run is None:
                raise ValueError("WorkflowRun does not belong to workspace")
            assert_transition_allowed(run.status, WorkflowStatus.RUNNING)
            run.status = WorkflowStatus.RUNNING
            await uow.commit()
        return await self.advance(workspace_id=workspace_id, workflow_run_id=workflow_run_id)

    async def retry_failed_step(self, *, workspace_id: UUID, workflow_run_id: UUID) -> WorkflowRunResult:
        async with KnowledgeUnitOfWork(self._session_factory) as uow:
            assert uow.session is not None
            run = await uow.workflow_runs.get_by_id(workspace_id, workflow_run_id)
            if run is None:
                raise ValueError("WorkflowRun does not belong to workspace")
            failed_step = (
                await uow.session.execute(
                    select(WorkflowStepRun)
                    .where(
                        WorkflowStepRun.workspace_id == workspace_id,
                        WorkflowStepRun.workflow_run_id == workflow_run_id,
                        WorkflowStepRun.status == WorkflowStatus.FAILED,
                    )
                    .order_by(WorkflowStepRun.sequence)
                    .limit(1)
                )
            ).scalar_one_or_none()
            if failed_step is None:
                return await _result_for_run(uow.session, run)
            assert_transition_allowed(run.status, WorkflowStatus.RUNNING)
            run.status = WorkflowStatus.RUNNING
            run.error = None
            failed_step.status = WorkflowStatus.PENDING
            failed_step.error_type = None
            failed_step.error_message = None
            await uow.commit()
        return await self.advance(workspace_id=workspace_id, workflow_run_id=workflow_run_id)

    async def _start_next_step(self, workspace_id: UUID, workflow_run_id: UUID) -> tuple[WorkflowRun, WorkflowStepRun | None, dict[str, dict]]:
        async with KnowledgeUnitOfWork(self._session_factory) as uow:
            assert uow.session is not None
            run = await uow.workflow_runs.get_by_id(workspace_id, workflow_run_id)
            if run is None:
                raise ValueError("WorkflowRun does not belong to workspace")
            if run.status in {WorkflowStatus.COMPLETED, WorkflowStatus.SUCCEEDED, WorkflowStatus.REQUIRES_APPROVAL, WorkflowStatus.CANCELLED}:
                return run, None, await _step_outputs(uow.session, workspace_id, workflow_run_id)
            if run.status == WorkflowStatus.PAUSED:
                return run, None, await _step_outputs(uow.session, workspace_id, workflow_run_id)
            if run.status in {WorkflowStatus.READY, WorkflowStatus.PENDING, WorkflowStatus.FAILED}:
                assert_transition_allowed(run.status, WorkflowStatus.RUNNING)
                run.status = WorkflowStatus.RUNNING

            steps = await uow.workflow_steps.list_for_workflow(workspace_id, workflow_run_id)
            previous_outputs = {step.step_key: step.output_payload for step in steps if step.status == WorkflowStatus.SUCCEEDED}
            next_step = next((step for step in steps if step.status in {WorkflowStatus.PENDING, WorkflowStatus.FAILED}), None)
            if next_step is None:
                assert_transition_allowed(run.status, WorkflowStatus.COMPLETED)
                run.status = WorkflowStatus.COMPLETED
                run.current_step = None
                run.completed_at = datetime.now(UTC)
                await uow.commit()
                return run, None, previous_outputs

            next_step.status = WorkflowStatus.RUNNING
            next_step.attempt += 1
            next_step.started_at = datetime.now(UTC)
            next_step.error_type = None
            next_step.error_message = None
            next_step.input_payload = {
                "workflow_input": run.input,
                "previous_outputs": previous_outputs,
            }
            run.current_step = next_step.step_key
            await uow.commit()
            return run, next_step, previous_outputs

    async def _complete_step(self, workspace_id: UUID, workflow_run_id: UUID, step_id: UUID, result: StepHandlerResult) -> WorkflowRunResult:
        async with KnowledgeUnitOfWork(self._session_factory) as uow:
            assert uow.session is not None
            run = await uow.workflow_runs.get_by_id(workspace_id, workflow_run_id)
            step = await uow.workflow_steps.get_by_id(workspace_id, step_id)
            if run is None or step is None or step.workflow_run_id != workflow_run_id:
                raise ValueError("Workflow step does not belong to workspace")
            step.status = WorkflowStatus.SUCCEEDED
            step.output_payload = {
                **result.output_payload,
                "output_kind": result.output_kind,
                "requires_approval": result.requires_approval,
            }
            step.completed_at = datetime.now(UTC)
            if result.requires_approval:
                assert_transition_allowed(run.status, WorkflowStatus.REQUIRES_APPROVAL)
                run.status = WorkflowStatus.REQUIRES_APPROVAL
                run.current_step = None
            await uow.commit()
        if result.requires_approval:
            return await self._get_result(workspace_id, workflow_run_id)
        return await self.advance(workspace_id=workspace_id, workflow_run_id=workflow_run_id)

    async def _fail_step(self, workspace_id: UUID, workflow_run_id: UUID, step_id: UUID, exc: Exception) -> None:
        async with KnowledgeUnitOfWork(self._session_factory) as uow:
            run = await uow.workflow_runs.get_by_id(workspace_id, workflow_run_id)
            step = await uow.workflow_steps.get_by_id(workspace_id, step_id)
            if run is None or step is None or step.workflow_run_id != workflow_run_id:
                raise ValueError("Workflow step does not belong to workspace")
            step.status = WorkflowStatus.FAILED
            step.completed_at = datetime.now(UTC)
            step.error_type = exc.__class__.__name__
            step.error_message = str(exc)[:2000]
            assert_transition_allowed(run.status, WorkflowStatus.FAILED)
            run.status = WorkflowStatus.FAILED
            run.error = step.error_message
            await uow.commit()

    async def _get_result(self, workspace_id: UUID, workflow_run_id: UUID) -> WorkflowRunResult:
        async with KnowledgeUnitOfWork(self._session_factory) as uow:
            assert uow.session is not None
            run = await uow.workflow_runs.get_by_id(workspace_id, workflow_run_id)
            if run is None:
                raise ValueError("WorkflowRun does not belong to workspace")
            return await _result_for_run(uow.session, run)


async def _step_outputs(session, workspace_id: UUID, workflow_run_id: UUID) -> dict[str, dict]:
    steps = (
        await session.execute(
            select(WorkflowStepRun)
            .where(
                WorkflowStepRun.workspace_id == workspace_id,
                WorkflowStepRun.workflow_run_id == workflow_run_id,
                WorkflowStepRun.status == WorkflowStatus.SUCCEEDED,
            )
            .order_by(WorkflowStepRun.sequence)
        )
    ).scalars()
    return {step.step_key: step.output_payload for step in steps}


async def _result_for_run(session, run: WorkflowRun) -> WorkflowRunResult:
    return WorkflowRunResult(
        workflow_run_id=run.id,
        status=run.status,
        current_step=run.current_step,
        step_outputs=await _step_outputs(session, run.workspace_id, run.id),
        error=run.error,
    )
