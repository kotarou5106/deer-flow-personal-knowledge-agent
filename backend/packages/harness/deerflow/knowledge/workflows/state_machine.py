from __future__ import annotations

from deerflow.knowledge.enums import WorkflowStatus

_TRANSITIONS: dict[WorkflowStatus, set[WorkflowStatus]] = {
    WorkflowStatus.DRAFT: {WorkflowStatus.READY, WorkflowStatus.CANCELLED},
    WorkflowStatus.READY: {WorkflowStatus.RUNNING, WorkflowStatus.CANCELLED},
    WorkflowStatus.PENDING: {WorkflowStatus.READY, WorkflowStatus.RUNNING, WorkflowStatus.CANCELLED},
    WorkflowStatus.RUNNING: {
        WorkflowStatus.COMPLETED,
        WorkflowStatus.SUCCEEDED,
        WorkflowStatus.PAUSED,
        WorkflowStatus.FAILED,
        WorkflowStatus.REQUIRES_APPROVAL,
        WorkflowStatus.CANCELLED,
    },
    WorkflowStatus.PAUSED: {WorkflowStatus.RUNNING, WorkflowStatus.CANCELLED},
    WorkflowStatus.FAILED: {WorkflowStatus.RUNNING, WorkflowStatus.CANCELLED},
    WorkflowStatus.REQUIRES_APPROVAL: {WorkflowStatus.RUNNING, WorkflowStatus.COMPLETED, WorkflowStatus.CANCELLED},
    WorkflowStatus.COMPLETED: set(),
    WorkflowStatus.SUCCEEDED: set(),
    WorkflowStatus.CANCELLED: set(),
}


def assert_transition_allowed(current: WorkflowStatus, target: WorkflowStatus) -> None:
    if target == current:
        return
    allowed = _TRANSITIONS.get(current, set())
    if target not in allowed:
        raise ValueError(f"Illegal workflow status transition: {current} -> {target}")
