from __future__ import annotations

import json
import math
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|token|cookie|password|secret)\s*[:=]\s*['\"]?[^'\"\s]+"),
    re.compile(r"(?i)postgres(?:ql)?://[^@\s]+@"),
    re.compile(r"(?i)bearer\s+[a-z0-9._~+/=-]{12,}"),
)


@dataclass(frozen=True)
class EvaluationOutput:
    report: dict[str, Any]
    markdown: str


def load_dataset(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        dataset = json.load(handle)
    if dataset.get("suite_version") != "2026-06-18":
        raise ValueError("Unsupported evaluation dataset suite_version")
    return dataset


def run_evaluation(dataset: dict[str, Any], *, commit: str | None = None, timestamp: datetime | None = None) -> EvaluationOutput:
    generated_at = timestamp or datetime.now(UTC)
    metrics: dict[str, Any] = {
        "retrieval": _evaluate_retrieval(dataset["retrieval_cases"]),
        "citation_integrity": _evaluate_citations(dataset["citation_cases"]),
        "analysis": _evaluate_analysis(dataset["analysis_cases"]),
        "revision_conflict": _evaluate_revision_conflict(dataset["revision_conflict_cases"]),
        "workflow_artifact": _evaluate_boolean_cases(dataset["workflow_artifact_cases"]),
        "approval_action": _evaluate_boolean_cases(dataset["approval_action_cases"]),
        "security_adversarial": _evaluate_boolean_cases(dataset["security_adversarial_cases"]),
        "performance_baseline": _evaluate_performance(dataset["performance_baseline"]),
    }
    failed_cases = _failed_cases(metrics)
    warnings = _warnings(metrics)
    report = {
        "suite_version": dataset["suite_version"],
        "commit": commit or _current_commit(),
        "timestamp": generated_at.replace(microsecond=0).isoformat(),
        "environment": {
            "python": "3.12+",
            "database": "not_required_for_fixture_evaluation",
            "external_network": "disabled",
            "model_provider": "deterministic_fixture",
        },
        "datasets": {
            "retrieval_cases": len(dataset["retrieval_cases"]),
            "citation_cases": len(dataset["citation_cases"]),
            "analysis_cases": len(dataset["analysis_cases"]),
            "revision_conflict_cases": len(dataset["revision_conflict_cases"]),
            "workflow_artifact_cases": len(dataset["workflow_artifact_cases"]),
            "approval_action_cases": len(dataset["approval_action_cases"]),
            "security_adversarial_cases": len(dataset["security_adversarial_cases"]),
        },
        "metrics": metrics,
        "cases_passed": _count_passed(metrics),
        "cases_failed": len(failed_cases),
        "warnings": warnings,
        "security_findings": _security_findings(metrics),
        "residual_risks": dataset.get("residual_risks", []),
    }
    markdown = render_markdown_report(report)
    _assert_no_secrets(report, markdown)
    return EvaluationOutput(report=report, markdown=markdown)


def write_reports(output: EvaluationOutput, json_path: str | Path, markdown_path: str | Path) -> None:
    json_target = Path(json_path)
    markdown_target = Path(markdown_path)
    json_target.parent.mkdir(parents=True, exist_ok=True)
    markdown_target.parent.mkdir(parents=True, exist_ok=True)
    json_target.write_text(json.dumps(output.report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    markdown_target.write_text(output.markdown, encoding="utf-8")


def render_markdown_report(report: dict[str, Any]) -> str:
    metrics = report["metrics"]
    retrieval = metrics["retrieval"]["aggregate"]
    citation = metrics["citation_integrity"]["aggregate"]
    analysis = metrics["analysis"]["aggregate"]
    revision = metrics["revision_conflict"]["aggregate"]
    workflow = metrics["workflow_artifact"]["aggregate"]
    approval = metrics["approval_action"]["aggregate"]
    security = metrics["security_adversarial"]["aggregate"]
    performance = metrics["performance_baseline"]
    return "\n".join(
        [
            "# Personal Knowledge Agent Evaluation",
            "",
            "## Executive Summary",
            f"- Cases passed: {report['cases_passed']}",
            f"- Cases failed: {report['cases_failed']}",
            f"- Security findings: {len(report['security_findings'])}",
            "",
            "## Evaluation Scope",
            "Fixed fixtures cover retrieval, citation integrity, analysis classification, revision/conflict outcomes, workflow/artifact invariants, approval/action invariants, and adversarial security boundaries.",
            "",
            "## Dataset",
            _json_table(report["datasets"]),
            "",
            "## Retrieval Metrics",
            f"- Recall@K: {_pct(retrieval['recall_at_k'])}",
            f"- Precision@K: {_pct(retrieval['precision_at_k'])}",
            f"- MRR: {_pct(retrieval['mrr'])}",
            f"- Citation hit rate: {_pct(retrieval['citation_hit_rate'])}",
            "",
            "## Citation Integrity",
            f"- Coverage: {_pct(citation['coverage'])}",
            f"- Precision: {_pct(citation['precision'])}",
            f"- Offset exactness: {_pct(citation['offset_exactness'])}",
            "",
            "## Analysis Results",
            f"- Classification accuracy: {_pct(analysis['classification_accuracy'])}",
            f"- Unsupported assertion rate: {_pct(analysis['unsupported_assertion_rate'])}",
            f"- Citation-backed fact rate: {_pct(analysis['citation_backed_fact_rate'])}",
            "",
            "## Revision / Conflict Results",
            f"- Case accuracy: {_pct(revision['case_accuracy'])}",
            "",
            "## Workflow / Artifact Results",
            f"- Invariant pass rate: {_pct(workflow['pass_rate'])}",
            "",
            "## Approval / Action Results",
            f"- Invariant pass rate: {_pct(approval['pass_rate'])}",
            "",
            "## Security Findings",
            f"- Adversarial pass rate: {_pct(security['pass_rate'])}",
            f"- Failed adversarial cases: {', '.join(security['failed_case_ids']) or 'none'}",
            "",
            "## Known Limitations",
            *[f"- {item}" for item in report["residual_risks"]],
            "",
            "## Performance Baseline",
            f"- Evaluation fixture target: {performance['max_evaluation_runtime_ms']} ms",
            f"- P95 retrieval target: {performance['retrieval_p95_ms']} ms",
            "",
            "## Reproduction Commands",
            "- `cd backend && uv run python scripts/run_personal_knowledge_evaluation.py`",
            "- `cd backend && uv run pytest tests/knowledge/test_evaluation_harness.py tests/knowledge/test_security_adversarial.py -q`",
            "",
        ]
    )


def _evaluate_retrieval(cases: list[dict[str, Any]]) -> dict[str, Any]:
    results = []
    for case in cases:
        gold = set(case["gold_evidence_ids"])
        predicted = case["ranked_evidence_ids"][: case["k"]]
        predicted_set = set(predicted)
        hit_positions = [index + 1 for index, item in enumerate(predicted) if item in gold]
        results.append(
            {
                "case_id": case["case_id"],
                "channels": case["channels"],
                "recall_at_k": len(predicted_set & gold) / len(gold) if gold else None,
                "precision_at_k": len(predicted_set & gold) / len(predicted) if predicted else None,
                "mrr": 1 / min(hit_positions) if hit_positions else 0.0,
                "citation_hit_rate": 1.0 if case["expected_citation_id"] in predicted_set else 0.0,
                "workspace_isolated": case.get("workspace_isolated", False),
                "parent_expansion_direct_evidence_only": case.get("parent_expansion_direct_evidence_only", False),
            }
        )
    return {"cases": results, "aggregate": _aggregate_numeric(results, ["recall_at_k", "precision_at_k", "mrr", "citation_hit_rate"])}


def _evaluate_citations(cases: list[dict[str, Any]]) -> dict[str, Any]:
    results = []
    for case in cases:
        valid = []
        for citation in case["citations"]:
            offset_exact = case["chunk_content"][citation["start_offset"] : citation["end_offset"]] == citation["quoted_text"]
            valid.append(
                offset_exact and citation["workspace_id"] == case["workspace_id"] and citation["revision_id"] in case["allowed_revision_ids"] and citation["direct_evidence"] is True and citation["metadata_rebuilt_by_server"] is True
            )
        supported = [item for item in case["facts"] if item["classification"] == "SupportedFact"]
        cited_supported = [item for item in supported if item.get("citation_ids")]
        results.append(
            {
                "case_id": case["case_id"],
                "coverage": len(cited_supported) / len(supported) if supported else 1.0,
                "precision": sum(valid) / len(valid) if valid else 1.0,
                "offset_exactness": sum(1 for item in case["citations"] if case["chunk_content"][item["start_offset"] : item["end_offset"]] == item["quoted_text"]) / len(case["citations"]),
                "passed": all(valid) and len(cited_supported) == len(supported),
            }
        )
    return {"cases": results, "aggregate": _aggregate_numeric(results, ["coverage", "precision", "offset_exactness"])}


def _evaluate_analysis(cases: list[dict[str, Any]]) -> dict[str, Any]:
    results = []
    for case in cases:
        expected = [item["expected_classification"] for item in case["statements"]]
        predicted = [item["predicted_classification"] for item in case["statements"]]
        unsupported = [item for item in case["statements"] if item["predicted_classification"] == "UnsupportedClaim"]
        facts = [item for item in case["statements"] if item["predicted_classification"] == "SupportedFact"]
        backed = [item for item in facts if item.get("citation_ids")]
        results.append(
            {
                "case_id": case["case_id"],
                "classification_accuracy": sum(1 for left, right in zip(expected, predicted, strict=True) if left == right) / len(expected),
                "unsupported_assertion_rate": len(unsupported) / len(predicted),
                "citation_backed_fact_rate": len(backed) / len(facts) if facts else 1.0,
                "passed": expected == predicted and len(backed) == len(facts),
            }
        )
    return {"cases": results, "aggregate": _aggregate_numeric(results, ["classification_accuracy", "unsupported_assertion_rate", "citation_backed_fact_rate"])}


def _evaluate_revision_conflict(cases: list[dict[str, Any]]) -> dict[str, Any]:
    results = []
    for case in cases:
        revision_match = case["expected_revision_changes"] == case["actual_revision_changes"]
        conflict_match = case["expected_conflict_classification"] == case["actual_conflict_classification"]
        results.append({"case_id": case["case_id"], "passed": revision_match and conflict_match})
    aggregate = {"case_accuracy": sum(1 for item in results if item["passed"]) / len(results) if results else None}
    return {"cases": results, "aggregate": aggregate}


def _evaluate_boolean_cases(cases: list[dict[str, Any]]) -> dict[str, Any]:
    results = [{"case_id": case["case_id"], "passed": all(case["assertions"].values()), "failed_assertions": [key for key, value in case["assertions"].items() if not value]} for case in cases]
    aggregate = {
        "pass_rate": sum(1 for item in results if item["passed"]) / len(results) if results else None,
        "failed_case_ids": [item["case_id"] for item in results if not item["passed"]],
    }
    return {"cases": results, "aggregate": aggregate}


def _evaluate_performance(baseline: dict[str, Any]) -> dict[str, Any]:
    return {
        "max_evaluation_runtime_ms": baseline["max_evaluation_runtime_ms"],
        "retrieval_p95_ms": baseline["retrieval_p95_ms"],
        "status": "baseline_recorded_not_benchmarked",
    }


def _aggregate_numeric(results: list[dict[str, Any]], keys: list[str]) -> dict[str, Any]:
    aggregate = {}
    for key in keys:
        values = [item[key] for item in results if item.get(key) is not None]
        aggregate[key] = sum(values) / len(values) if values else None
    return aggregate


def _count_passed(metrics: dict[str, Any]) -> int:
    total = 0
    for value in metrics.values():
        for case in value.get("cases", []) if isinstance(value, dict) else []:
            total += 1 if case.get("passed", True) else 0
    return total


def _failed_cases(metrics: dict[str, Any]) -> list[str]:
    failed = []
    for value in metrics.values():
        for case in value.get("cases", []) if isinstance(value, dict) else []:
            if case.get("passed") is False:
                failed.append(str(case["case_id"]))
    return failed


def _warnings(metrics: dict[str, Any]) -> list[str]:
    warnings = []
    channels = {channel for case in metrics["retrieval"]["cases"] for channel in case["channels"]}
    for required in {"lexical", "vector", "graph", "rrf", "parent_expansion"} - channels:
        warnings.append(f"Retrieval channel fixture missing: {required}")
    if metrics["performance_baseline"]["status"] == "baseline_recorded_not_benchmarked":
        warnings.append("Performance numbers are fixture baselines, not live benchmarks.")
    return warnings


def _security_findings(metrics: dict[str, Any]) -> list[dict[str, Any]]:
    findings = []
    for case in metrics["security_adversarial"]["cases"]:
        if not case["passed"]:
            findings.append({"case_id": case["case_id"], "severity": "high", "failed_assertions": case["failed_assertions"]})
    return findings


def _pct(value: float | None) -> str:
    if value is None or math.isnan(value):
        return "N/A"
    return f"{value * 100:.1f}%"


def _json_table(value: dict[str, Any]) -> str:
    return "\n".join(f"- {key}: {item}" for key, item in value.items())


def _current_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return "unknown"


def _assert_no_secrets(report: dict[str, Any], markdown: str) -> None:
    payload = json.dumps(report, ensure_ascii=False) + "\n" + markdown
    for pattern in SECRET_PATTERNS:
        if pattern.search(payload):
            raise ValueError("Evaluation report contains a secret-like value")
    home = os.path.expanduser("~")
    if home and home != "/" and home in payload:
        raise ValueError("Evaluation report contains a local private path")
