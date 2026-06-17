from __future__ import annotations

from deerflow.knowledge.actions.adapter import (
    ActionAdapter,
    FakeArtifactExportAdapter,
    FakeCalendarAdapter,
    FakeEmailAdapter,
    FakeTaskAdapter,
)


class ActionAdapterRegistry:
    def __init__(self, adapters: dict[str, ActionAdapter] | None = None) -> None:
        self._adapters = dict(adapters or {})

    @property
    def names(self) -> set[str]:
        return set(self._adapters)

    def register(self, connector_type: str, adapter: ActionAdapter) -> None:
        self._adapters[connector_type] = adapter

    def get(self, connector_type: str) -> ActionAdapter:
        adapter = self._adapters.get(connector_type)
        if adapter is None:
            raise ValueError(f"Missing action adapter: {connector_type}")
        return adapter


def default_fake_action_adapter_registry() -> ActionAdapterRegistry:
    return ActionAdapterRegistry(
        {
            "email": FakeEmailAdapter(),
            "calendar": FakeCalendarAdapter(),
            "task": FakeTaskAdapter(),
            "artifact_export": FakeArtifactExportAdapter(),
        }
    )
