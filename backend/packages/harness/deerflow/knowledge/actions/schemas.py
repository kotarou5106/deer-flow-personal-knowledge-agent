from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import StrEnum
from uuid import UUID

from deerflow.knowledge.enums import RiskLevel


class ActionType(StrEnum):
    EMAIL_DRAFT = "email_draft"
    EMAIL_SEND = "email_send"
    CALENDAR_DRAFT = "calendar_draft"
    CALENDAR_CREATE = "calendar_create"
    TASK_CREATE = "task_create"
    ARTIFACT_EXPORT = "artifact_export"


EXTERNAL_WRITE_ACTIONS = {ActionType.EMAIL_SEND, ActionType.CALENDAR_CREATE, ActionType.TASK_CREATE}


@dataclass(frozen=True)
class ActionDraft:
    action_type: ActionType
    target: str
    payload: dict
    preview: dict
    risk_level: RiskLevel
    requires_approval: bool
    source_workflow_run_id: UUID
    source_step_run_id: UUID | None = None
    artifact_ids: tuple[UUID, ...] = ()
    evidence_ids: tuple[UUID, ...] = ()


@dataclass(frozen=True)
class ValidatedAction:
    action_type: ActionType
    target: str
    payload: dict
    preview: dict
    risk_level: RiskLevel
    requires_approval: bool
    source_workflow_run_id: UUID
    source_step_run_id: UUID | None = None
    artifact_ids: tuple[UUID, ...] = ()
    evidence_ids: tuple[UUID, ...] = ()
    payload_hash: str = ""


@dataclass(frozen=True)
class ApprovalResult:
    approval_request_id: UUID
    status: str
    action_payload_hash: str


@dataclass(frozen=True)
class ExecutionResult:
    approval_request_id: UUID
    action_execution_id: UUID | None
    status: str
    adapter_called: bool
    external_reference: str | None = None
    error: str | None = None
    requires_reconciliation: bool = False


@dataclass(frozen=True)
class ActionAdapterResult:
    succeeded: bool
    external_reference: str | None = None
    result_payload: dict = field(default_factory=dict)
    error_message: str | None = None
    requires_reconciliation: bool = False


def validate_action_draft(raw: ActionDraft | dict) -> ValidatedAction:
    if isinstance(raw, ActionDraft):
        payload = {
            "action_type": raw.action_type,
            "target": raw.target,
            "payload": raw.payload,
            "preview": raw.preview,
            "risk_level": raw.risk_level,
            "requires_approval": raw.requires_approval,
            "source_workflow_run_id": raw.source_workflow_run_id,
            "source_step_run_id": raw.source_step_run_id,
            "artifact_ids": raw.artifact_ids,
            "evidence_ids": raw.evidence_ids,
        }
    else:
        payload = raw

    try:
        action_type = ActionType(payload["action_type"])
    except Exception as exc:
        raise ValueError("Unknown action type") from exc
    try:
        risk_level = RiskLevel(payload["risk_level"])
    except Exception as exc:
        raise ValueError("Invalid action risk level") from exc

    target = str(payload.get("target") or "").strip()
    if not target:
        raise ValueError("Action target is required")
    action_payload = payload.get("payload")
    preview = payload.get("preview")
    if not isinstance(action_payload, dict):
        raise ValueError("Action payload must be an object")
    if not isinstance(preview, dict):
        raise ValueError("Action preview must be an object")

    requires_approval = bool(payload.get("requires_approval"))
    if action_type in EXTERNAL_WRITE_ACTIONS and not requires_approval:
        raise ValueError("External write actions require approval")

    workflow_run_id = _coerce_uuid(payload.get("source_workflow_run_id"), "source_workflow_run_id")
    source_step_run_id = _coerce_optional_uuid(payload.get("source_step_run_id"), "source_step_run_id")
    artifact_ids = tuple(_coerce_uuid(item, "artifact_ids") for item in payload.get("artifact_ids", ()))
    evidence_ids = tuple(_coerce_uuid(item, "evidence_ids") for item in payload.get("evidence_ids", ()))

    validated = ValidatedAction(
        action_type=action_type,
        target=target,
        payload=action_payload,
        preview=preview,
        risk_level=risk_level,
        requires_approval=requires_approval,
        source_workflow_run_id=workflow_run_id,
        source_step_run_id=source_step_run_id,
        artifact_ids=artifact_ids,
        evidence_ids=evidence_ids,
    )
    return ValidatedAction(**{**validated.__dict__, "payload_hash": action_payload_hash(validated)})


def action_payload_hash(action: ValidatedAction) -> str:
    canonical = {
        "action_type": action.action_type.value,
        "target": action.target,
        "payload": _redact_sensitive(action.payload),
        "preview": _redact_sensitive(action.preview),
        "risk_level": action.risk_level.value,
        "requires_approval": action.requires_approval,
        "source_workflow_run_id": str(action.source_workflow_run_id),
        "source_step_run_id": str(action.source_step_run_id) if action.source_step_run_id else None,
        "artifact_ids": [str(item) for item in action.artifact_ids],
        "evidence_ids": [str(item) for item in action.evidence_ids],
    }
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def action_payload_for_storage(action: ValidatedAction) -> dict:
    return {
        "action_type": action.action_type.value,
        "target": action.target,
        "payload": _redact_sensitive(action.payload),
        "preview": _redact_sensitive(action.preview),
        "risk_level": action.risk_level.value,
        "requires_approval": action.requires_approval,
        "source_workflow_run_id": str(action.source_workflow_run_id),
        "source_step_run_id": str(action.source_step_run_id) if action.source_step_run_id else None,
        "artifact_ids": [str(item) for item in action.artifact_ids],
        "evidence_ids": [str(item) for item in action.evidence_ids],
    }


def _coerce_uuid(value: object, field_name: str) -> UUID:
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except Exception as exc:
        raise ValueError(f"{field_name} must be a UUID") from exc


def _coerce_optional_uuid(value: object, field_name: str) -> UUID | None:
    if value in (None, ""):
        return None
    return _coerce_uuid(value, field_name)


def _redact_sensitive(value):
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            key_text = str(key).lower()
            if any(token in key_text for token in ("secret", "token", "password", "api_key", "apikey", "credential")):
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = _redact_sensitive(item)
        return redacted
    if isinstance(value, list):
        return [_redact_sensitive(item) for item in value]
    return value
