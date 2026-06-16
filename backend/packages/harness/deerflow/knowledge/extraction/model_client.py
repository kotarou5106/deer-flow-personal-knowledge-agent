from __future__ import annotations

import asyncio
from typing import Protocol

from pydantic import ValidationError

from deerflow.knowledge.extraction.prompts import build_messages
from deerflow.knowledge.extraction.schemas import ModelExtractionRequest, StructuredExtractionOutput
from deerflow.models.factory import create_chat_model


class ExtractionModelNotConfiguredError(RuntimeError):
    pass


class StructuredExtractionModel(Protocol):
    @property
    def model_identity(self) -> str: ...

    async def extract(self, request: ModelExtractionRequest) -> StructuredExtractionOutput: ...


class LangChainStructuredExtractionModel:
    def __init__(self, *, model_name: str | None = None, timeout_seconds: float = 60.0, max_retries: int = 1) -> None:
        if model_name is None:
            raise ExtractionModelNotConfiguredError("Structured extraction requires an explicit model_name or injected model client")
        self._model_name = model_name
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._model = create_chat_model(model_name, thinking_enabled=False, attach_tracing=True)
        if not hasattr(self._model, "with_structured_output"):
            raise ExtractionModelNotConfiguredError(f"Model {model_name} does not support structured output")
        self._structured_model = self._model.with_structured_output(StructuredExtractionOutput)

    @property
    def model_identity(self) -> str:
        return self._model_name

    async def extract(self, request: ModelExtractionRequest) -> StructuredExtractionOutput:
        messages = build_messages(request)
        last_error: Exception | None = None
        for _ in range(self._max_retries + 1):
            try:
                result = await asyncio.wait_for(self._structured_model.ainvoke(messages), timeout=self._timeout_seconds)
                if isinstance(result, StructuredExtractionOutput):
                    return result
                return StructuredExtractionOutput.model_validate(result)
            except (TimeoutError, ValidationError, ValueError) as exc:
                last_error = exc
        raise RuntimeError(f"Structured extraction model failed: {last_error}") from last_error
