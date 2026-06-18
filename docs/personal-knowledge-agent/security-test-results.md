# Personal Knowledge Agent Security Test Results

Last updated: 2026-06-18

## Scope

This record covers the Evaluation / Security close-out checks for the current `feat/knowledge-evaluation-security-e2e` branch.

Out of scope:

- Real Gmail, Calendar, task, export, and model-backed connector dispatch.
- Production deployment.
- Main branch merge.

## Results

### Focused Adversarial Tests

Command:

```bash
cd backend
uv run pytest tests/knowledge/test_evaluation_harness.py tests/knowledge/test_security_adversarial.py -q
```

Result:

- `7 passed, 1 warning`

Coverage:

- Prompt injection source text remains untrusted evidence.
- SSRF rejects loopback, private, metadata, userinfo, and private DNS results.
- `/mnt/user-data/...` virtual paths cannot escape the user storage root.
- Server-managed fields are rejected in nested mutation payloads, including the final workflow input regression for nested `owner_id`.
- Knowledge mutations require formal CSRF.

### Live PostgreSQL Gateway Security Check

Command shape:

```bash
cd backend
PYTHONPATH=. PKA_LIVE_SECURITY_DATABASE_URL=... uv run pytest /tmp/pka_live_security_check.py -q
```

Result:

- `1 passed, 1 warning`

Verified through formal Gateway app lifespan, trusted context, temporary PostgreSQL, pgvector, and durable worker configuration:

- Top-level and nested `workspace_id`, `user_id`, `thread_id`, `actor_id`, `owner_id`, `approval_status`, `execution_status`, and `payload_hash` are rejected.
- Source, Artifact, Workflow, Approval, ActionExecution, and AuditLog reads are workspace-isolated.
- Unapproved action execution is rejected.
- Payload mutation after approval invalidates execution.
- `RECONCILIATION_REQUIRED` action outcome persists.
- AuditLog payloads do not store database URLs, passwords, cookies, token assignments, API-key-like values, tracebacks, or full source payloads.

### Microsoft Edge Malicious Rendering Smoke

Command:

```bash
node /tmp/pka_edge_xss_smoke.mjs
```

Result:

- Passed with system Microsoft Edge.

Checked surfaces:

- Source
- Analysis
- Artifact Markdown
- Citation
- Action Preview

Injected payloads:

- `<script>...</script>`
- `<img src=x onerror=...>`
- `javascript:` URLs

Observed result:

- No script execution.
- No event handler execution.
- No dialogs.
- `javascript:` URL was blocked to `#blocked`.

## Secret and Path Hygiene

Reports regenerated with:

```bash
cd backend
uv run python scripts/run_personal_knowledge_evaluation.py
```

Report scan result:

- `artifacts/personal-knowledge-agent-evaluation.json`: no secret-like or local private path matches.
- `artifacts/personal-knowledge-agent-evaluation.md`: no secret-like or local private path matches.
- Frontend production bundle scan: no PostgreSQL connection URL, Knowledge database URL, token/cookie assignment, or secret-like runtime credential matches in the generated bundle. Next's untracked `required-server-files` build metadata contains expected local build paths and is not committed.

## Final Regression Snapshot

- Live Gateway jobs PostgreSQL: `4 passed, 1 warning`.
- Live Knowledge full-stack PostgreSQL: `6 passed, 1 warning`.
- Live PostgreSQL security check: `1 passed, 1 warning`.
- Evaluation/Security focused backend: `7 passed, 1 warning`.
- Backend Knowledge suite: `120 passed, 16 skipped, 1 warning`.
- Backend lint: passed.
- Backend full test: `4563 passed, 32 skipped, 11 warnings`.
- Frontend unit tests: `339 passed`.
- Frontend typecheck: passed.
- Frontend lint: passed.
- Frontend production build: passed with existing Turbopack NFT trace and localstorage-file warnings.
- Frontend demo/static build: passed with existing Turbopack NFT trace and localstorage-file warnings.

## Temporary Resource Cleanup

The live PostgreSQL container, volume, temporary connection secret file, and `/tmp` smoke scripts are removed after verification. No Gateway, Worker, Next dev server, or test PostgreSQL process should remain running.
