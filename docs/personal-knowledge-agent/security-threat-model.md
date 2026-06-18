# Personal Knowledge Agent Security Threat Model

Last updated: 2026-06-18

This threat model covers the Personal Knowledge Agent surfaces that are implemented in the current repository: Gateway Knowledge API, durable jobs, deterministic ingestion/retrieval/analysis/workflow services, approvals, fake action adapters, frontend Knowledge client, and user-scoped file paths. Real Gmail, Calendar, task, external export, and model-backed connectors remain out of scope because they are not integrated.

## Assets

- Knowledge Sources: `Source`, `SourceSnapshot`, `DocumentRevision`, and stored source metadata in PostgreSQL.
- Revisions: current and historical document revisions, chunk hashes, parser version, and status.
- Claims: extracted structured claims and claim lifecycle status.
- Evidence: chunks, evidence spans, citation metadata, provenance, and offsets.
- Artifacts: workflow artifacts, markdown previews, JSON payloads, staleness state, and evidence links.
- Approvals: approval requests, decisions, payload hashes, status, and risk level.
- Actions: fake action drafts, execution records, idempotency keys, adapter outcomes, and reconciliation state.
- Audit Logs: approval and action history exposed through `/api/knowledge/audit`.
- Workspace Identity: trusted user, actor, thread, workspace UUID, and storage root derived server-side.
- User Files: `/mnt/user-data/...` virtual paths resolved through `deerflow.config.paths.Paths`.
- Credentials: auth cookies, CSRF token, internal owner headers, database URLs, and future connector secrets.

## Trust Boundaries

- Browser -> Gateway: HTTP requests, cookies, CSRF headers, Knowledge client payloads, and rendered API data.
- Gateway -> Worker: persisted durable jobs, job payloads, trusted context, retries, idempotency, and SSE events.
- Worker -> PostgreSQL: job claim leases, Knowledge writes, workflow state, approvals, action executions, and audit logs.
- Gateway/Worker -> File Parser: uploaded file paths, media types, malformed documents, empty files, and size limits.
- Gateway/Worker -> URL Fetcher: user-provided URLs, redirects, DNS resolution, content length, and response bytes.
- Domain -> Model Provider: evidence context packs, prompt-injection-bearing document text, and deterministic/future model output.
- Approval -> Action Adapter: approved action drafts, payload hashes, idempotency keys, fake adapter outcomes, and future external side effects.

## Threat Actors

- Unauthenticated attacker sending requests without a valid Gateway session or internal auth context.
- Malicious workspace member attempting IDOR, replay, mass assignment, or cross-workspace reads.
- Malicious uploaded document containing prompt injection, scripts, path tricks, malformed content, or oversized payloads.
- Malicious remote webpage attempting SSRF, redirect-to-private, metadata access, or instruction injection.
- Compromised external provider returning hostile or misleading data.
- Accidental operator error such as leaking config, running with wrong environment variables, or publishing local test artifacts.

## Threat Matrix

| Threat | Entry Point | Existing Control | Test Coverage | Residual Risk | Required Fix |
| --- | --- | --- | --- | --- | --- |
| Prompt Injection | Uploaded documents, URL content, retrieved chunks, model responses | Analysis prompts wrap evidence as untrusted data; citation validator rebuilds server metadata; parent context cannot support facts alone | `backend/tests/knowledge/test_analysis_grounding.py`, `backend/tests/knowledge/test_security_adversarial.py`, fixture case `prompt-injection-documents-remain-untrusted` | Future real model providers can still produce unsafe text and must remain behind validator and citation policy | Before external models ship, add provider-specific red-team fixtures and fail closed on unsafe tool/action requests |
| SSRF | URL ingestion and redirects in `ContentAcquirer._acquire_url` | `assert_safe_http_url` rejects non-http schemes, userinfo, localhost, private/link-local/reserved IPs, unsafe DNS results; redirects are revalidated before fetch | `backend/tests/knowledge/test_ingestion_source_acquisition.py`, `backend/tests/knowledge/test_security_adversarial.py`, fixture case `ssrf-url-boundaries` | DNS rebinding TOCTOU is not fully eliminated by the current resolver/fetch split | Use a filtering transport or pinned-address connector before high-risk remote ingestion is enabled broadly |
| IDOR | Source, revision, claim, conflict, artifact, workflow, approval, action, audit routes | Gateway derives `TrustedKnowledgeContext`; repository and provider reads include `workspace_id`; unknown/cross-workspace IDs become not-found style errors | `backend/tests/knowledge/test_gateway_jobs.py`, live PostgreSQL Knowledge tests, fixture case `auth-csrf-idor-mass-assignment` | New future endpoints could forget workspace scoping | Add an IDOR regression for every new Knowledge route before exposing it in production UI |
| CSRF | Mutating Knowledge routes: ingestion, workflow, artifacts, approvals, actions | Gateway `CSRFMiddleware` requires `X-CSRF-Token` matching CSRF cookie for mutations; frontend transport sends the header | `backend/tests/knowledge/test_gateway_jobs.py`, `backend/tests/knowledge/test_security_adversarial.py`, `frontend/tests/unit/core/knowledge/transport.test.ts` | Non-browser internal clients must continue using formal internal auth plus CSRF where required | Keep CSRF middleware on Gateway mutations; document any explicit non-browser exemption before adding one |
| XSS | Source content, analysis output, artifact markdown, quoted citations, action previews, error messages | React default escaping; Knowledge UI renders markdown preview text conservatively; frontend avoids fabricated HTML execution in Knowledge surfaces | `frontend/tests/unit/core/knowledge/client.test.ts`, `frontend/tests/unit/core/artifacts/preview.test.ts`, fixture case `xss-rendering-boundaries`, system Microsoft Edge malicious rendering smoke | Shared AI elements include `dangerouslySetInnerHTML` for syntax-highlighted code; this must remain fed only by sanitized highlighter output | Keep browser XSS smoke in the release gate and add connector-specific rendering cases before real external content providers ship |
| Mass Assignment | JSON bodies for ingestion, analysis, workflow, approvals, action preview/execute | Pydantic `extra="forbid"` and recursive server-managed field rejection for trusted identity/status/hash fields; frontend client recursively blocks the same fields | `backend/tests/knowledge/test_gateway_jobs.py`, `backend/tests/knowledge/test_security_adversarial.py`, `frontend/tests/unit/core/knowledge/client.test.ts` | Future public request fields may accidentally collide with server-owned state | Keep the denylist centralized when adding new action/approval statuses |
| Path Traversal | `/mnt/user-data/...` virtual file ingestion and artifact storage paths | `Paths.resolve_virtual_path` requires exact virtual prefix and verifies resolved path stays under user/thread root; user and thread IDs are charset validated | `backend/tests/test_local_sandbox_virtual_path_contract.py`, `backend/tests/knowledge/test_security_adversarial.py`, fixture case `file-upload-boundaries` | Parser libraries may create temp files outside this helper if future code bypasses it | Require all Knowledge file paths to enter through `Paths` or upload manager helpers |
| Payload Tampering | Approval/action draft mutation after approval | Server computes canonical payload hash; preview reports staleness; execute rejects stale payloads; approval does not equal execution success | `backend/tests/knowledge/test_fullstack_integration_live_postgres.py`, `backend/tests/knowledge/test_gateway_jobs.py`, fixture case `approval-action-invariants` | Future real connectors must bind execution request to the stored approved payload, not a client copy | Execute stored drafts by default and require explicit audited re-approval for changed payloads |
| Replay Attack | Repeated job, workflow, approval, or action execution requests | Job/workflow idempotency keys; action execution idempotency; row locking/concurrency protection in live PostgreSQL tests | `backend/tests/knowledge/test_gateway_jobs.py`, `backend/tests/knowledge/test_fullstack_integration_live_postgres.py`, fixture case `approval-action-invariants` | Idempotency key quality depends on caller for some routes | Generate server-side idempotency keys for high-risk future external actions |
| Privilege Escalation | Forged `workspace_id`, `user_id`, `owner_id`, approval/action status, or internal headers | Trusted context comes from auth dependency; public body schemas reject trusted/server-managed fields; internal auth helpers are test-only or configured server-side | `backend/tests/knowledge/test_gateway_jobs.py`, `backend/tests/knowledge/test_security_adversarial.py`, `frontend/tests/unit/core/knowledge/client.test.ts` | Misconfigured auth-disabled deployments are unsafe outside local/dev | Keep auth-disabled mode documented as local-only and fail closed in production configs |
| Data Exfiltration | Prompt injection, URL fetches, logs, reports, frontend bundles | No real external connectors; SSRF blocks private targets; evaluation report scanner rejects secret-like values and local private paths | `backend/tests/knowledge/test_evaluation_harness.py`, `backend/tests/knowledge/test_security_adversarial.py`, fixture reports in `artifacts/` | Future connectors introduce real exfiltration paths | Add connector-specific egress allowlists and audit logs before real connector enablement |
| Race Condition | Concurrent job claims, workflow retries, action execution | Durable job lease/claim semantics; action execution row locking and idempotency; bounded worker shutdown | `backend/tests/knowledge/test_gateway_jobs.py`, live PostgreSQL Gateway/Full-stack tests, fixture case `approval-action-invariants` | SQLite focused tests cannot prove all PostgreSQL lock semantics | Keep live PostgreSQL concurrency tests in the required release gate |

## Security Gate

The current stage is considered locally verified only when these pass:

- `cd backend && uv run pytest tests/knowledge/test_evaluation_harness.py tests/knowledge/test_security_adversarial.py -q`
- `cd backend && uv run python scripts/run_personal_knowledge_evaluation.py`
- `cd backend && uv run pytest tests/knowledge -q`
- `make -C backend lint`
- `make -C backend test`
- `npx pnpm@10.26.2 --dir frontend test -- tests/unit/core/knowledge/client.test.ts`
- system Microsoft Edge malicious Knowledge rendering smoke against Source, Analysis, Artifact Markdown, Citation, and Action Preview surfaces

The generated reports are:

- `artifacts/personal-knowledge-agent-evaluation.json`
- `artifacts/personal-knowledge-agent-evaluation.md`
