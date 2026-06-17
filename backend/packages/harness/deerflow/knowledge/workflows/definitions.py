from __future__ import annotations

from deerflow.knowledge.workflows.schemas import ArtifactOutputDefinition, InputSchema, WorkflowDefinition, WorkflowStepDefinition, WorkflowType


def _steps(*pairs: tuple[str, str]) -> tuple[WorkflowStepDefinition, ...]:
    return tuple(WorkflowStepDefinition(step_key=step_key, sequence=index, handler_name=handler) for index, (step_key, handler) in enumerate(pairs))


WORKFLOW_DEFINITIONS: tuple[WorkflowDefinition, ...] = (
    WorkflowDefinition(
        workflow_type=WorkflowType.TOPIC_DOSSIER,
        input_schema=InputSchema(required_fields=("topic", "user_id", "thread_id"), optional_fields=("filters", "context_budget")),
        ordered_steps=_steps(("retrieve_evidence", "retrieve_evidence"), ("analyze_evidence", "analyze_evidence"), ("persist_artifact", "persist_artifact")),
        required_handlers=("retrieve_evidence", "analyze_evidence", "persist_artifact"),
        artifact_outputs=(ArtifactOutputDefinition("topic_dossier", "Topic Dossier: {topic}"),),
        completion_conditions=("all_steps_succeeded", "artifact_persisted"),
        whether_external_action_may_follow=False,
    ),
    WorkflowDefinition(
        workflow_type=WorkflowType.PROJECT_CONTEXT_PACK,
        input_schema=InputSchema(required_fields=("project", "user_id", "thread_id"), optional_fields=("filters", "context_budget")),
        ordered_steps=_steps(("retrieve_evidence", "retrieve_evidence"), ("analyze_evidence", "analyze_evidence"), ("persist_artifact", "persist_artifact")),
        required_handlers=("retrieve_evidence", "analyze_evidence", "persist_artifact"),
        artifact_outputs=(ArtifactOutputDefinition("project_context_pack", "Project Context Pack: {project}"),),
        completion_conditions=("all_steps_succeeded", "artifact_persisted"),
        whether_external_action_may_follow=False,
    ),
    WorkflowDefinition(
        workflow_type=WorkflowType.READING_SYNTHESIS,
        input_schema=InputSchema(required_fields=("reading_set", "user_id", "thread_id"), optional_fields=("question", "filters")),
        ordered_steps=_steps(("retrieve_evidence", "retrieve_evidence"), ("analyze_evidence", "analyze_evidence"), ("persist_artifact", "persist_artifact")),
        required_handlers=("retrieve_evidence", "analyze_evidence", "persist_artifact"),
        artifact_outputs=(ArtifactOutputDefinition("reading_synthesis", "Reading Synthesis"),),
        completion_conditions=("all_steps_succeeded", "artifact_persisted"),
        whether_external_action_may_follow=False,
    ),
    WorkflowDefinition(
        workflow_type=WorkflowType.DECISION_MEMO,
        input_schema=InputSchema(required_fields=("decision", "user_id", "thread_id"), optional_fields=("options", "filters")),
        ordered_steps=_steps(("retrieve_evidence", "retrieve_evidence"), ("analyze_evidence", "analyze_evidence"), ("persist_artifact", "persist_artifact")),
        required_handlers=("retrieve_evidence", "analyze_evidence", "persist_artifact"),
        artifact_outputs=(ArtifactOutputDefinition("decision_memo", "Decision Memo: {decision}"),),
        completion_conditions=("all_steps_succeeded", "artifact_persisted"),
        whether_external_action_may_follow=False,
    ),
    WorkflowDefinition(
        workflow_type=WorkflowType.MEETING_PREPARATION,
        input_schema=InputSchema(required_fields=("meeting", "user_id", "thread_id"), optional_fields=("attendees", "filters")),
        ordered_steps=_steps(("retrieve_evidence", "retrieve_evidence"), ("analyze_evidence", "analyze_evidence"), ("persist_artifact", "persist_artifact")),
        required_handlers=("retrieve_evidence", "analyze_evidence", "persist_artifact"),
        artifact_outputs=(ArtifactOutputDefinition("meeting_preparation", "Meeting Preparation: {meeting}"),),
        completion_conditions=("all_steps_succeeded", "artifact_persisted"),
        whether_external_action_may_follow=False,
    ),
    WorkflowDefinition(
        workflow_type=WorkflowType.KNOWLEDGE_UPDATE_REVIEW,
        input_schema=InputSchema(required_fields=("source_id", "old_revision_id", "new_revision_id", "user_id", "thread_id"), optional_fields=()),
        ordered_steps=_steps(("review_knowledge_update", "review_knowledge_update"), ("persist_artifact", "persist_artifact")),
        required_handlers=("review_knowledge_update", "persist_artifact"),
        artifact_outputs=(ArtifactOutputDefinition("knowledge_update_review", "Knowledge Update Review"),),
        completion_conditions=("all_steps_succeeded", "artifact_persisted"),
        whether_external_action_may_follow=False,
    ),
    WorkflowDefinition(
        workflow_type=WorkflowType.KNOWLEDGE_TO_ACTION,
        input_schema=InputSchema(required_fields=("objective", "user_id", "thread_id"), optional_fields=("risk_level", "filters")),
        ordered_steps=_steps(("retrieve_evidence", "retrieve_evidence"), ("analyze_evidence", "analyze_evidence"), ("create_action_draft", "create_action_draft"), ("persist_artifact", "persist_artifact")),
        required_handlers=("retrieve_evidence", "analyze_evidence", "create_action_draft", "persist_artifact"),
        artifact_outputs=(ArtifactOutputDefinition("action_draft", "Action Draft: {objective}"),),
        completion_conditions=("all_steps_succeeded", "requires_approval_not_execution"),
        whether_external_action_may_follow=True,
    ),
)
