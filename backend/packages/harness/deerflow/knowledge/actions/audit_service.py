from __future__ import annotations

from uuid import UUID

from deerflow.knowledge.models import AuditLog
from deerflow.knowledge.unit_of_work import KnowledgeUnitOfWork, SessionFactory


class ActionAuditService:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    async def append(
        self,
        *,
        workspace_id: UUID,
        actor_id: str | None,
        event_type: str,
        target_type: str,
        target_id: str,
        payload: dict,
    ) -> None:
        async with KnowledgeUnitOfWork(self._session_factory) as uow:
            assert uow.session is not None
            uow.session.add(
                AuditLog(
                    workspace_id=workspace_id,
                    actor_id=actor_id,
                    event_type=event_type,
                    target_type=target_type,
                    target_id=target_id,
                    payload=_redact(payload),
                )
            )
            await uow.commit()


def _redact(value):
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            key_text = str(key).lower()
            if any(token in key_text for token in ("secret", "token", "password", "api_key", "apikey", "credential")):
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = _redact(item)
        return redacted
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value
