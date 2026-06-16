from __future__ import annotations

import pytest

from deerflow.knowledge.extraction.entity_resolver import entity_types_compatible, normalize_entity_key
from deerflow.knowledge.extraction.model_client import ExtractionModelNotConfiguredError
from deerflow.knowledge.extraction.service import ExtractionService


def test_entity_key_normalization_is_conservative_and_exact() -> None:
    assert normalize_entity_key("  Ａｃｍｅ   Corp  ") == normalize_entity_key("Acme Corp")
    assert normalize_entity_key("Acme Corporation") != normalize_entity_key("Acme Corp")


def test_entity_type_compatibility_requires_exact_normalized_type() -> None:
    assert entity_types_compatible("Organization", " organization ")
    assert not entity_types_compatible("person", "organization")


def test_extraction_service_requires_configured_model_or_injected_fake() -> None:
    with pytest.raises(ExtractionModelNotConfiguredError, match="explicit model_name or injected model client"):
        ExtractionService(lambda: None)
