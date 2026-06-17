from __future__ import annotations

from deerflow.knowledge.enums import ApprovalStatus

_ALLOWED: dict[ApprovalStatus, set[ApprovalStatus]] = {
    ApprovalStatus.DRAFT: {ApprovalStatus.AWAITING_APPROVAL, ApprovalStatus.CANCELLED},
    ApprovalStatus.AWAITING_APPROVAL: {ApprovalStatus.APPROVED, ApprovalStatus.REJECTED, ApprovalStatus.CANCELLED},
    ApprovalStatus.APPROVED: {ApprovalStatus.EXECUTING, ApprovalStatus.CANCELLED},
    ApprovalStatus.EXECUTING: {ApprovalStatus.SUCCEEDED, ApprovalStatus.FAILED},
    ApprovalStatus.SUCCEEDED: set(),
    ApprovalStatus.FAILED: set(),
    ApprovalStatus.REJECTED: set(),
    ApprovalStatus.CANCELLED: set(),
}


def assert_approval_transition_allowed(current: ApprovalStatus | str, target: ApprovalStatus | str) -> None:
    current_status = ApprovalStatus(current)
    target_status = ApprovalStatus(target)
    if target_status not in _ALLOWED[current_status]:
        raise ValueError(f"Illegal approval status transition: {current_status} -> {target_status}")
