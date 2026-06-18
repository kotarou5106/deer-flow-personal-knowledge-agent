from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from deerflow.knowledge.evaluation import load_dataset, run_evaluation, write_reports

DATASET = Path(__file__).parents[1] / "fixtures/knowledge/evaluation_dataset.json"


def test_evaluation_dataset_computes_required_metrics_and_reports_without_failures() -> None:
    dataset = load_dataset(DATASET)
    output = run_evaluation(dataset, commit="test-commit", timestamp=datetime(2026, 6, 18, tzinfo=UTC))

    metrics = output.report["metrics"]
    assert metrics["retrieval"]["aggregate"]["recall_at_k"] == pytest.approx(1.0)
    assert metrics["retrieval"]["aggregate"]["precision_at_k"] == pytest.approx(0.4166666667)
    assert metrics["retrieval"]["aggregate"]["mrr"] == pytest.approx(0.75)
    assert metrics["retrieval"]["aggregate"]["citation_hit_rate"] == pytest.approx(1.0)
    assert metrics["citation_integrity"]["aggregate"] == {
        "coverage": 1.0,
        "precision": 1.0,
        "offset_exactness": 1.0,
    }
    assert metrics["analysis"]["aggregate"]["classification_accuracy"] == pytest.approx(1.0)
    assert metrics["analysis"]["aggregate"]["unsupported_assertion_rate"] == pytest.approx(0.25)
    assert metrics["analysis"]["aggregate"]["citation_backed_fact_rate"] == pytest.approx(1.0)
    assert {case["case_id"] for case in metrics["revision_conflict"]["cases"]} >= {
        "revision-all-change-types-direct-contradiction",
        "revision-temporal-source-scope-possible-insufficient",
        "revision-source-disagreement",
        "revision-scope-or-condition-difference",
        "revision-possible-conflict",
        "revision-insufficient-evidence",
    }
    assert metrics["workflow_artifact"]["aggregate"]["pass_rate"] == pytest.approx(1.0)
    assert metrics["approval_action"]["aggregate"]["pass_rate"] == pytest.approx(1.0)
    assert metrics["security_adversarial"]["aggregate"]["pass_rate"] == pytest.approx(1.0)
    assert output.report["cases_failed"] == 0
    assert "Executive Summary" in output.markdown
    assert ("postgresql" + "://") not in json.dumps(output.report).casefold()
    assert "/Users/" not in output.markdown


def test_evaluation_report_writer_creates_machine_and_human_readable_artifacts(tmp_path: Path) -> None:
    output = run_evaluation(load_dataset(DATASET), commit="test-commit", timestamp=datetime(2026, 6, 18, tzinfo=UTC))
    json_path = tmp_path / "evaluation.json"
    markdown_path = tmp_path / "evaluation.md"

    write_reports(output, json_path, markdown_path)

    assert json.loads(json_path.read_text(encoding="utf-8"))["suite_version"] == "2026-06-18"
    rendered = markdown_path.read_text(encoding="utf-8")
    assert "Retrieval Metrics" in rendered
    assert "Reproduction Commands" in rendered
