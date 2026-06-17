from __future__ import annotations

from deerflow.knowledge.actions.schemas import EXTERNAL_WRITE_ACTIONS, ActionType, ValidatedAction


def requires_approval(action_type: ActionType) -> bool:
    return action_type in EXTERNAL_WRITE_ACTIONS


def connector_type_for(action: ValidatedAction) -> str:
    if action.action_type in {ActionType.EMAIL_DRAFT, ActionType.EMAIL_SEND}:
        return "email"
    if action.action_type in {ActionType.CALENDAR_DRAFT, ActionType.CALENDAR_CREATE}:
        return "calendar"
    if action.action_type == ActionType.TASK_CREATE:
        return "task"
    if action.action_type == ActionType.ARTIFACT_EXPORT:
        return "artifact_export"
    raise ValueError("Unsupported action type")
