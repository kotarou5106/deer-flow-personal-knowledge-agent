from __future__ import annotations

from deerflow.knowledge.workflows.schemas import StepHandler


class HandlerRegistry:
    def __init__(self, handlers: dict[str, StepHandler] | None = None) -> None:
        self._handlers = dict(handlers or {})

    @property
    def names(self) -> set[str]:
        return set(self._handlers)

    def register(self, name: str, handler: StepHandler) -> None:
        self._handlers[name] = handler

    def get(self, name: str) -> StepHandler:
        try:
            return self._handlers[name]
        except KeyError:
            raise ValueError(f"Workflow handler is not registered: {name}") from None
