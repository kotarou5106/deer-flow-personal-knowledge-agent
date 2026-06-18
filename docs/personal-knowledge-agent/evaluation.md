# Personal Knowledge Agent Evaluation

Last updated: 2026-06-18

This stage adds a deterministic fixture evaluation suite for the completed Personal Knowledge Agent surfaces. It does not call external model APIs, Gmail, Calendar, task systems, export connectors, or the public network.

## Dataset

The fixture dataset lives at:

- `backend/tests/fixtures/knowledge/evaluation_dataset.json`

It covers:

- Retrieval cases for lexical retrieval, vector retrieval, graph retrieval, Reciprocal Rank Fusion, parent expansion, and workspace isolation.
- Citation cases for coverage, precision, server-rebuilt metadata, direct evidence, workspace scope, revision scope, and offset exactness.
- Analysis cases for `SupportedFact`, `InferredConclusion`, `UnsupportedClaim`, and `UnresolvedQuestion`.
- Revision and conflict cases for `UNCHANGED`, `ADDED`, `REMOVED`, `MODIFIED`, `MOVED`, `DIRECT_CONTRADICTION`, `TEMPORAL_UPDATE`, `SCOPE_OR_CONDITION_DIFFERENCE`, `SOURCE_DISAGREEMENT`, `POSSIBLE_CONFLICT`, and `INSUFFICIENT_EVIDENCE`.
- Workflow/artifact invariants.
- Approval/action invariants.
- Prompt injection, SSRF, upload, auth/CSRF/IDOR/mass-assignment, and XSS adversarial cases.

## Runner

The runner lives at:

- `backend/packages/harness/deerflow/knowledge/evaluation.py`
- `backend/scripts/run_personal_knowledge_evaluation.py`

Run:

```bash
cd backend
uv run python scripts/run_personal_knowledge_evaluation.py
```

Generated reports:

- `artifacts/personal-knowledge-agent-evaluation.json`
- `artifacts/personal-knowledge-agent-evaluation.md`

The report writer rejects secret-like values and local private paths before writing reports.

## Metrics

Current deterministic fixture result:

- Cases passed: 17
- Cases failed: 0
- Recall@K: 100.0%
- Precision@K: 41.7%
- MRR: 75.0%
- Citation hit rate: 100.0%
- Citation coverage: 100.0%
- Citation precision: 100.0%
- Offset exactness: 100.0%
- Analysis classification accuracy: 100.0%
- Unsupported assertion rate: 25.0%
- Citation-backed fact rate: 100.0%
- Revision/conflict case accuracy: 100.0%
- Workflow/artifact invariant pass rate: 100.0%
- Approval/action invariant pass rate: 100.0%
- Security adversarial pass rate: 100.0%

## Verification Commands

```bash
cd backend
uv run pytest tests/knowledge/test_evaluation_harness.py tests/knowledge/test_security_adversarial.py -q
uv run pytest tests/knowledge -q
make -C .. -C backend lint
```

Frontend security client checks:

```bash
npx pnpm@10.26.2 --dir frontend test -- tests/unit/core/knowledge/client.test.ts
```

## Limitations

- This is a fixed fixture evaluation, not a human-labeled real-model quality benchmark.
- Performance values are small local baselines, not load-test results.
- Real connector security remains future scope because real Gmail, Calendar, task, export, and model-backed external dispatch are intentionally not integrated.
