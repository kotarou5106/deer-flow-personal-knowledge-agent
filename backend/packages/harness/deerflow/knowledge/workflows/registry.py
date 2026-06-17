from __future__ import annotations

from deerflow.knowledge.workflows.definitions import WORKFLOW_DEFINITIONS
from deerflow.knowledge.workflows.schemas import WorkflowDefinition, WorkflowType


class WorkflowDefinitionRegistry:
    def __init__(self, definitions: tuple[WorkflowDefinition, ...] = WORKFLOW_DEFINITIONS) -> None:
        self._definitions = {definition.workflow_type: definition for definition in definitions}

    def get(self, workflow_type: WorkflowType | str) -> WorkflowDefinition:
        key = WorkflowType(workflow_type)
        try:
            return self._definitions[key]
        except KeyError:
            raise ValueError(f"Unknown workflow type: {workflow_type}") from None

    def list(self) -> tuple[WorkflowDefinition, ...]:
        return tuple(self._definitions.values())

    def validate_handlers(self, definition: WorkflowDefinition, handler_names: set[str]) -> None:
        missing = [name for name in definition.required_handlers if name not in handler_names]
        if missing:
            raise ValueError(f"Missing workflow handler(s): {', '.join(missing)}")
