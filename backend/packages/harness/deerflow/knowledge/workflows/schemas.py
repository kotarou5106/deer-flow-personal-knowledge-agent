from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol
from uuid import UUID

WORKFLOW_ENGINE_NAME = "knowledge_workflow_engine"
WORKFLOW_ENGINE_VERSION = "1"


class WorkflowType(StrEnum):
    TOPIC_DOSSIER = "topic_dossier"
    PROJECT_CONTEXT_PACK = "project_context_pack"
    READING_SYNTHESIS = "reading_synthesis"
    DECISION_MEMO = "decision_memo"
    MEETING_PREPARATION = "meeting_preparation"
    KNOWLEDGE_UPDATE_REVIEW = "knowledge_update_review"
    KNOWLEDGE_TO_ACTION = "knowledge_to_action"


class StepOutputKind(StrEnum):
    DATA = "data"
    ARTIFACT_REQUEST = "artifact_request"
    ACTION_DRAFT = "action_draft"


@dataclass(frozen=True)
class InputSchema:
    required_fields: tuple[str, ...]
    optional_fields: tuple[str, ...] = ()

    def validate(self, payload: dict) -> None:
        missing = [field_name for field_name in self.required_fields if field_name not in payload or payload[field_name] in (None, "")]
        if missing:
            raise ValueError(f"Missing required workflow input field(s): {', '.join(missing)}")


@dataclass(frozen=True)
class WorkflowStepDefinition:
    step_key: str
    sequence: int
    handler_name: str


@dataclass(frozen=True)
class ArtifactOutputDefinition:
    artifact_type: str
    title_template: str
    formats: tuple[str, ...] = ("json", "markdown")


@dataclass(frozen=True)
class WorkflowDefinition:
    workflow_type: WorkflowType
    input_schema: InputSchema
    ordered_steps: tuple[WorkflowStepDefinition, ...]
    required_handlers: tuple[str, ...]
    artifact_outputs: tuple[ArtifactOutputDefinition, ...]
    completion_conditions: tuple[str, ...]
    whether_external_action_may_follow: bool


@dataclass(frozen=True)
class StepHandlerContext:
    workspace_id: UUID
    workflow_run_id: UUID
    step_key: str
    input_payload: dict
    previous_outputs: dict[str, dict]
    attempt: int


@dataclass(frozen=True)
class StepHandlerResult:
    output_payload: dict
    output_kind: StepOutputKind = StepOutputKind.DATA
    requires_approval: bool = False


class StepHandler(Protocol):
    async def __call__(self, context: StepHandlerContext) -> StepHandlerResult: ...


@dataclass(frozen=True)
class ArtifactWriteRequest:
    workspace_id: UUID
    workflow_run_id: UUID
    user_id: str
    thread_id: str
    artifact_type: str
    title: str
    json_payload: dict
    markdown: str
    evidence_span_ids: tuple[UUID, ...] = ()
    claim_ids: tuple[UUID, ...] = ()
    revision_ids: tuple[UUID, ...] = ()
    usage_type: str = "workflow_output"
    idempotency_key: str | None = None


@dataclass(frozen=True)
class ArtifactWriteResult:
    artifact_id: UUID
    storage_path: str
    markdown_storage_path: str
    evidence_link_count: int


@dataclass(frozen=True)
class WorkflowRunResult:
    workflow_run_id: UUID
    status: str
    current_step: str | None
    step_outputs: dict[str, dict] = field(default_factory=dict)
    error: str | None = None
