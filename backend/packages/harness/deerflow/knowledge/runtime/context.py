from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from deerflow.config.paths import get_paths
from deerflow.runtime.user_context import resolve_runtime_user_id


@dataclass(frozen=True)
class TrustedKnowledgeContext:
    user_id: str
    workspace_id: UUID
    thread_id: str
    actor_id: str
    storage_root: Path


def _context_dict(runtime: Any) -> dict:
    context = getattr(runtime, "context", None)
    return context if isinstance(context, dict) else {}


def _runtime_config_dict(runtime: Any) -> dict:
    config = getattr(runtime, "config", None)
    return config if isinstance(config, dict) else {}


def _resolve_thread_id(runtime: Any, context: dict) -> str:
    thread_id = context.get("thread_id")
    if thread_id:
        return str(thread_id)
    config_thread_id = (_runtime_config_dict(runtime).get("configurable") or {}).get("thread_id")
    if config_thread_id:
        return str(config_thread_id)
    raise ValueError("Trusted thread_id is not available in runtime context")


def _resolve_workspace_id(context: dict) -> UUID:
    workspace_id = context.get("workspace_id")
    if workspace_id is None:
        raise ValueError("Trusted workspace_id is not available in runtime context")
    try:
        return workspace_id if isinstance(workspace_id, UUID) else UUID(str(workspace_id))
    except (TypeError, ValueError) as exc:
        raise ValueError("Trusted workspace_id is invalid") from exc


def resolve_trusted_knowledge_context(runtime: Any) -> TrustedKnowledgeContext:
    context = _context_dict(runtime)
    thread_id = _resolve_thread_id(runtime, context)
    user_id = resolve_runtime_user_id(runtime)
    actor_id = str(context.get("actor_id") or user_id)
    workspace_id = _resolve_workspace_id(context)
    storage_root = get_paths().sandbox_user_data_dir(thread_id, user_id=user_id)
    return TrustedKnowledgeContext(
        user_id=user_id,
        workspace_id=workspace_id,
        thread_id=thread_id,
        actor_id=actor_id,
        storage_root=storage_root,
    )
