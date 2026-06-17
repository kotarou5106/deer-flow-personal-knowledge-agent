from __future__ import annotations

from typing import Protocol

from deerflow.knowledge.actions.schemas import ActionAdapterResult, ValidatedAction


class ActionAdapter(Protocol):
    async def execute(self, action: ValidatedAction, idempotency_key: str) -> ActionAdapterResult: ...


class RecordingFakeAdapter:
    def __init__(
        self,
        *,
        succeed: bool = True,
        timeout: bool = False,
        uncertain: bool = False,
        external_reference_prefix: str = "fake",
    ) -> None:
        self.calls: list[tuple[ValidatedAction, str]] = []
        self.succeed = succeed
        self.timeout = timeout
        self.uncertain = uncertain
        self.external_reference_prefix = external_reference_prefix

    async def execute(self, action: ValidatedAction, idempotency_key: str) -> ActionAdapterResult:
        self.calls.append((action, idempotency_key))
        if self.timeout:
            raise TimeoutError("adapter timed out")
        if self.uncertain:
            return ActionAdapterResult(False, error_message="adapter result is unknown", requires_reconciliation=True)
        if not self.succeed:
            return ActionAdapterResult(False, error_message="adapter failed")
        return ActionAdapterResult(
            True,
            external_reference=f"{self.external_reference_prefix}:{idempotency_key}",
            result_payload={"ok": True},
        )


class FakeEmailAdapter(RecordingFakeAdapter):
    def __init__(self, **kwargs) -> None:
        super().__init__(external_reference_prefix="email", **kwargs)


class FakeCalendarAdapter(RecordingFakeAdapter):
    def __init__(self, **kwargs) -> None:
        super().__init__(external_reference_prefix="calendar", **kwargs)


class FakeTaskAdapter(RecordingFakeAdapter):
    def __init__(self, **kwargs) -> None:
        super().__init__(external_reference_prefix="task", **kwargs)


class FakeArtifactExportAdapter(RecordingFakeAdapter):
    def __init__(self, **kwargs) -> None:
        super().__init__(external_reference_prefix="artifact_export", **kwargs)
