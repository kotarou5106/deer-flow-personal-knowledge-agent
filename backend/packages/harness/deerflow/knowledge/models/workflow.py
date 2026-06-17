from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKeyConstraint, Index, String, Text, UniqueConstraint, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from deerflow.knowledge.enums import ActionExecutionStatus, ApprovalStatus, RiskLevel, WorkflowStatus
from deerflow.knowledge.models.base import JSONB, KnowledgeBase, UUIDPrimaryKeyMixin, WorkspaceMixin, utc_now


class WorkflowRun(UUIDPrimaryKeyMixin, WorkspaceMixin, KnowledgeBase):
    __tablename__ = "knowledge_workflow_runs"

    workflow_type: Mapped[str] = mapped_column(String(128), nullable=False)
    input: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[WorkflowStatus] = mapped_column(
        Enum(WorkflowStatus, native_enum=False, create_constraint=True, name="knowledge_workflow_runs_status_check"),
        nullable=False,
        default=WorkflowStatus.PENDING,
    )
    current_step: Mapped[str | None] = mapped_column(String(128), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(256), nullable=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("id", "workspace_id", name="uq_knowledge_workflow_runs_id_workspace"),
        Index(
            "uq_knowledge_workflow_runs_idempotency",
            "workspace_id",
            "workflow_type",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
        Index("ix_knowledge_workflow_runs_workspace_status", "workspace_id", "status", "created_at"),
    )


class WorkflowStepRun(UUIDPrimaryKeyMixin, WorkspaceMixin, KnowledgeBase):
    __tablename__ = "knowledge_workflow_step_runs"

    workflow_run_id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    step_key: Mapped[str] = mapped_column(String(128), nullable=False)
    sequence: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[WorkflowStatus] = mapped_column(
        Enum(WorkflowStatus, native_enum=False, create_constraint=True, name="knowledge_workflow_step_runs_status_check"),
        nullable=False,
        default=WorkflowStatus.PENDING,
    )
    input_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    output_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    attempt: Mapped[int] = mapped_column(nullable=False, default=0)
    idempotency_key: Mapped[str] = mapped_column(String(256), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    __table_args__ = (
        UniqueConstraint("id", "workspace_id", name="uq_knowledge_workflow_step_runs_id_workspace"),
        UniqueConstraint("workflow_run_id", "step_key", name="uq_knowledge_workflow_steps_key"),
        UniqueConstraint("workflow_run_id", "sequence", name="uq_knowledge_workflow_steps_sequence"),
        UniqueConstraint("workspace_id", "idempotency_key", name="uq_knowledge_workflow_steps_idempotency"),
        CheckConstraint("sequence >= 0", name="ck_knowledge_workflow_steps_sequence_nonnegative"),
        CheckConstraint("attempt >= 0", name="ck_knowledge_workflow_steps_attempt_nonnegative"),
        ForeignKeyConstraint(
            ["workflow_run_id", "workspace_id"],
            ["knowledge_workflow_runs.id", "knowledge_workflow_runs.workspace_id"],
            name="fk_knowledge_workflow_steps_run_workspace",
            ondelete="CASCADE",
        ),
        Index("ix_knowledge_workflow_steps_workspace_run", "workspace_id", "workflow_run_id", "sequence"),
        Index("ix_knowledge_workflow_steps_workspace_status", "workspace_id", "status", "updated_at"),
    )


class WorkflowArtifact(UUIDPrimaryKeyMixin, WorkspaceMixin, KnowledgeBase):
    __tablename__ = "knowledge_workflow_artifacts"

    workflow_run_id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    artifact_id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("workflow_run_id", "artifact_id", name="uq_knowledge_workflow_artifact"),
        ForeignKeyConstraint(["workflow_run_id", "workspace_id"], ["knowledge_workflow_runs.id", "knowledge_workflow_runs.workspace_id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["artifact_id", "workspace_id"], ["knowledge_artifacts.id", "knowledge_artifacts.workspace_id"], ondelete="RESTRICT"),
    )


class ApprovalRequest(UUIDPrimaryKeyMixin, WorkspaceMixin, KnowledgeBase):
    __tablename__ = "knowledge_approval_requests"

    workflow_run_id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    source_step_run_id: Mapped[UUID | None] = mapped_column(postgresql.UUID(as_uuid=True), nullable=True)
    action_type: Mapped[str] = mapped_column(String(128), nullable=False)
    target: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    action_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    action_payload_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    action_preview: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    risk_level: Mapped[RiskLevel] = mapped_column(Enum(RiskLevel, native_enum=False, create_constraint=True), nullable=False, default=RiskLevel.LOW)
    status: Mapped[ApprovalStatus] = mapped_column(Enum(ApprovalStatus, native_enum=False, create_constraint=True), nullable=False, default=ApprovalStatus.DRAFT)
    requested_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("id", "workspace_id", name="uq_knowledge_approval_requests_id_workspace"),
        ForeignKeyConstraint(["workflow_run_id", "workspace_id"], ["knowledge_workflow_runs.id", "knowledge_workflow_runs.workspace_id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["source_step_run_id", "workspace_id"], ["knowledge_workflow_step_runs.id", "knowledge_workflow_step_runs.workspace_id"], ondelete="RESTRICT"),
        Index("ix_knowledge_approval_requests_workspace_status", "workspace_id", "status", "requested_at"),
        Index("ix_knowledge_approval_requests_workspace_hash", "workspace_id", "action_payload_hash"),
    )


class ActionExecution(UUIDPrimaryKeyMixin, WorkspaceMixin, KnowledgeBase):
    __tablename__ = "knowledge_action_executions"

    approval_request_id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    action_type: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    connector_type: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(256), nullable=False)
    action_payload_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    request_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    result_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[ActionExecutionStatus] = mapped_column(Enum(ActionExecutionStatus, native_enum=False, create_constraint=True), nullable=False, default=ActionExecutionStatus.PENDING)
    external_reference: Mapped[str | None] = mapped_column(String(512), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    requires_reconciliation: Mapped[bool] = mapped_column(nullable=False, default=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        UniqueConstraint("id", "workspace_id", name="uq_knowledge_action_executions_id_workspace"),
        UniqueConstraint("approval_request_id", name="uq_knowledge_action_executions_approval"),
        UniqueConstraint("workspace_id", "connector_type", "idempotency_key", name="uq_knowledge_action_executions_idempotency"),
        ForeignKeyConstraint(["approval_request_id", "workspace_id"], ["knowledge_approval_requests.id", "knowledge_approval_requests.workspace_id"], ondelete="RESTRICT"),
        Index("ix_knowledge_action_executions_workspace_status", "workspace_id", "status", "created_at"),
    )
