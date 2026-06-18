# Personal Knowledge Agent Evaluation

## Executive Summary
- Cases passed: 17
- Cases failed: 0
- Security findings: 0

## Evaluation Scope
Fixed fixtures cover retrieval, citation integrity, analysis classification, revision/conflict outcomes, workflow/artifact invariants, approval/action invariants, and adversarial security boundaries.

## Dataset
- retrieval_cases: 2
- citation_cases: 1
- analysis_cases: 1
- revision_conflict_cases: 6
- workflow_artifact_cases: 1
- approval_action_cases: 1
- security_adversarial_cases: 5

## Retrieval Metrics
- Recall@K: 100.0%
- Precision@K: 41.7%
- MRR: 75.0%
- Citation hit rate: 100.0%

## Citation Integrity
- Coverage: 100.0%
- Precision: 100.0%
- Offset exactness: 100.0%

## Analysis Results
- Classification accuracy: 100.0%
- Unsupported assertion rate: 25.0%
- Citation-backed fact rate: 100.0%

## Revision / Conflict Results
- Case accuracy: 100.0%

## Workflow / Artifact Results
- Invariant pass rate: 100.0%

## Approval / Action Results
- Invariant pass rate: 100.0%

## Security Findings
- Adversarial pass rate: 100.0%
- Failed adversarial cases: none

## Known Limitations
- Fixture evaluation is deterministic and does not replace future real-model quality evaluation with gold human labels.
- External Gmail, Calendar, task, export, and model connector security remains future scope because those connectors are intentionally not integrated.
- Performance entries are small local baselines, not production load-test results.

## Performance Baseline
- Evaluation fixture target: 500 ms
- P95 retrieval target: 150 ms

## Reproduction Commands
- `cd backend && uv run python scripts/run_personal_knowledge_evaluation.py`
- `cd backend && uv run pytest tests/knowledge/test_evaluation_harness.py tests/knowledge/test_security_adversarial.py -q`
