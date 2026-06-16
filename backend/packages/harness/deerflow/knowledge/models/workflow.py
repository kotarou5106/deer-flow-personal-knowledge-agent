from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKeyConstraint, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from deerflow.knowledge.enums import ActionExecutionStatus, ApprovalStatus, RiskLevel, WorkflowStatus
from deerflow.knowledge.models.base import JSONB, KnowledgeBase, UUIDPrimaryKeyMixin, WorkspaceMixin, utc_now


class WorkflowRun(UUIDPrimaryKeyMixin, WorkspaceMixin, KnowledgeBase):
    __tablename__ = "knowledge_workflow_runs"

    workflow_type: Mapped[str] = mapped_column(String(128), nullable=False)
    input: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[WorkflowStatus] = mapped_column(Enum(WorkflowStatus, native_enum=False, create_constraint=True), nullable=False, default=WorkflowStatus.PENDING)
    current_step: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("id", "workspace_id", name="uq_knowledge_workflow_runs_id_workspace"),
        Index("ix_knowledge_workflow_runs_workspace_status", "workspace_id", "status", "created_at"),
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
    action_type: Mapped[str] = mapped_column(String(128), nullable=False)
    action_preview: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    risk_level: Mapped[RiskLevel] = mapped_column(Enum(RiskLevel, native_enum=False, create_constraint=True), nullable=False, default=RiskLevel.LOW)
    status: Mapped[ApprovalStatus] = mapped_column(Enum(ApprovalStatus, native_enum=False, create_constraint=True), nullable=False, default=ApprovalStatus.DRAFT)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(128), nullable=True)

    __table_args__ = (
        UniqueConstraint("id", "workspace_id", name="uq_knowledge_approval_requests_id_workspace"),
        ForeignKeyConstraint(["workflow_run_id", "workspace_id"], ["knowledge_workflow_runs.id", "knowledge_workflow_runs.workspace_id"], ondelete="RESTRICT"),
        Index("ix_knowledge_approval_requests_workspace_status", "workspace_id", "status", "requested_at"),
    )


class ActionExecution(UUIDPrimaryKeyMixin, WorkspaceMixin, KnowledgeBase):
    __tablename__ = "knowledge_action_executions"

    approval_request_id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    connector_type: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(256), nullable=False)
    request_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    result_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[ActionExecutionStatus] = mapped_column(Enum(ActionExecutionStatus, native_enum=False, create_constraint=True), nullable=False, default=ActionExecutionStatus.PENDING)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        UniqueConstraint("id", "workspace_id", name="uq_knowledge_action_executions_id_workspace"),
        UniqueConstraint("workspace_id", "connector_type", "idempotency_key", name="uq_knowledge_action_executions_idempotency"),
        ForeignKeyConstraint(["approval_request_id", "workspace_id"], ["knowledge_approval_requests.id", "knowledge_approval_requests.workspace_id"], ondelete="RESTRICT"),
        Index("ix_knowledge_action_executions_workspace_status", "workspace_id", "status", "created_at"),
    )
