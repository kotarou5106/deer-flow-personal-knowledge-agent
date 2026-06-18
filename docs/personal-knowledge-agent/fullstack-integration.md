# Knowledge Full-Stack Integration

Last updated: 2026-06-18

This stage connects the Knowledge Workspace production UI to the project-owned Gateway and Knowledge APIs. It does not require OpenAI, Anthropic, Tavily, Firecrawl, DeepSeek, or any other external model/API service. Verification used fake/deterministic/local providers plus a temporary local pgvector PostgreSQL container.

Final unified acceptance is complete. The latest Knowledge Alembic head is `20260618_0006`, with a single revision chain from `20260616_0001` through `20260618_0006`.

## Completed Vertical Slice

- `POST /api/knowledge/ingestions` accepts browser file imports without trusted identity fields.
- Gateway derives trusted user, actor, thread, workspace, and storage root server-side.
- Gateway durable worker processes local file and URL jobs.
- `GET /api/knowledge/jobs/{job_id}/events` streams monotonic SSE events through terminal states.
- `GET /api/knowledge/sources`, `/overview`, and `/sources/{source_id}/detail` expose live source, revision, chunk, and job data.
- `POST /api/knowledge/search` returns retrieved chunks with provenance; the frontend maps those into citations.
- Workspace isolation is verified with separate trusted owner contexts.
- URL ingestion verifies SSRF rejection for blocked localhost URLs and a monkeypatched localhost-only happy path inside tests.
- `POST /api/knowledge/workflows`, `/workflows/{id}/advance`, `/pause`, `/resume`, and `/retry` now execute through the database-backed workflow engine instead of fake job fallbacks.
- Workflow detail/list responses include formal step payloads, trusted input metadata, artifact IDs, timestamps, and error state.
- Deterministic workflow handlers cover the current workflow types without external model calls: Topic Dossier, Project Context Pack, Reading Synthesis, Decision Memo, Meeting Preparation, Knowledge Update Review, and Knowledge-to-Action draft creation.
- Workflow artifacts can be generated and retrieved through `POST /api/knowledge/workflows/{id}/artifacts`, `GET /api/knowledge/artifacts/{id}`, and `GET /api/knowledge/artifacts/{id}/evidence-links`.
- Decision Memo and Project Context Pack artifacts include markdown preview content, workflow origin, stored JSON payload, and ArtifactEvidenceLink provenance back to evidence span, chunk, revision, source, and claim records.
- Knowledge-to-Action remains a draft boundary until explicit approval. It produces a non-executed action draft; `APPROVED` only means execution is allowed, not that execution has succeeded.
- Approval and fake action execution are now Gateway-backed in production mode: `POST /api/knowledge/approvals`, list/detail/decision routes, action preview, action execute, action execution detail, and related audit history.
- All supported action types execute through deterministic fake adapters only: `EMAIL_DRAFT`, `EMAIL_SEND`, `CALENDAR_DRAFT`, `CALENDAR_CREATE`, `TASK_CREATE`, and `ARTIFACT_EXPORT`.
- Server-side payload hash validation rejects stale action drafts after approval, idempotency prevents repeated fake side effects, and unknown adapter outcomes are represented as `RECONCILIATION_REQUIRED`.

## Frontend Runtime Fixes

- Production Knowledge read surfaces now load after browser hydration instead of caching server-side relative-fetch failures.
- Gateway transport binds `globalThis.fetch` so Chromium/Edge do not raise `Illegal invocation`.
- File import media type is inferred from the URI extension instead of hardcoding PDF.
- Production search maps real retrieved chunk provenance into citation drawer data.
- Error normalization preserves ordinary JavaScript error messages to keep local diagnostics actionable.
- Production Workflow UI uses the formal Gateway contracts for create, advance, pause, resume, retry, and artifact generation.
- Production Artifact detail renders Gateway markdown as text and surfaces provenance, workflow origin, validation, staleness, and evidence-link counts without fabricating unavailable data.
- Production Approvals UI lists real Gateway approval records, previews safe action summaries without side effects, approves/rejects through Gateway decisions, executes fake actions through the formal action endpoint, and shows persisted execution and audit state after refresh.
- Production Overview tolerates fresh workspaces without artifacts or conflicts, and production search renders duplicate retrieved candidates with stable keys.

## Verification

- `uv run ruff check app/gateway/deps.py packages/harness/deerflow/knowledge/runtime/provider.py tests/knowledge/test_fullstack_integration_live_postgres.py`
- `uv run python -m ruff check app/gateway/routers/knowledge.py packages/harness/deerflow/knowledge/runtime/provider.py packages/harness/deerflow/knowledge/workflows/state_machine.py tests/knowledge/test_gateway_jobs.py tests/knowledge/test_fullstack_integration_live_postgres.py`
- `uv run pytest tests/knowledge/test_gateway_jobs.py -q`
- `uv run pytest tests/knowledge -k 'workflow or artifact or gateway' -q`
- `KNOWLEDGE_FULLSTACK_TEST_DATABASE_URL=... uv run pytest tests/knowledge/test_fullstack_integration_live_postgres.py -q`
- `uv run pytest tests/knowledge -q`
- `make -C backend lint`
- `make -C backend test`
- `npx pnpm@10.26.2 test`
- `npx pnpm@10.26.2 --dir frontend exec tsc --noEmit`
- `npx pnpm@10.26.2 typecheck`
- `npx pnpm@10.26.2 lint`
- `NEXT_PUBLIC_KNOWLEDGE_DEMO_MODE=false npx pnpm@10.26.2 build`
- Microsoft Edge smoke against local Gateway + Next dev: UI import accepted, job succeeded, source appeared, search returned the ingested evidence.
- In-app browser smoke against local Gateway + Next dev in production Knowledge mode: Workflows page created a Decision Memo workflow, advanced it to `COMPLETED`, generated the artifact through the formal endpoint, and Artifacts page rendered workflow origin plus markdown preview without console errors.
- Approval/Fake Action focused backend: `uv run pytest tests/knowledge -k "approval or action or execution or gateway" -q` -> `47 passed, 6 skipped`.
- Approval/Fake Action live PostgreSQL: `KNOWLEDGE_FULLSTACK_TEST_DATABASE_URL=... uv run pytest tests/knowledge/test_fullstack_integration_live_postgres.py::test_approval_fake_action_fullstack_lifecycle_idempotency_and_audit -q` -> `1 passed`.
- Knowledge live full-stack PostgreSQL after Approval/Fake Action integration: `KNOWLEDGE_FULLSTACK_TEST_DATABASE_URL=... uv run pytest tests/knowledge/test_fullstack_integration_live_postgres.py -q` -> `6 passed`.
- Microsoft Edge smoke against local Gateway + Next dev in production Knowledge mode: Approvals page loaded real Gateway data, previewed a fake task action, approved it, executed the fake adapter, showed `APPROVED` separately from `SUCCEEDED`, survived page refresh, and remained usable at a narrow viewport.
- Frontend Knowledge focused tests: `npx pnpm@10.26.2 test -- tests/unit/core/knowledge` -> `339 passed`.
- Frontend full unit suite: `npx pnpm@10.26.2 test` -> `339 passed`.
- Backend Knowledge suite: `uv run pytest tests/knowledge -q` -> `112 passed, 16 skipped`.
- Backend full lint: `make lint` -> passed.
- Backend full test: `make test` -> `4555 passed, 32 skipped`.
- Final Alembic audit: one head, `20260618_0006`; history chain `20260616_0001 -> 20260617_0002 -> 20260617_0003 -> 20260617_0004 -> 20260617_0005 -> 20260618_0006`.
- Final formal Gateway jobs live PostgreSQL: `KNOWLEDGE_GATEWAY_JOB_TEST_DATABASE_URL=... uv run pytest tests/knowledge/test_gateway_jobs_live_postgres.py -q` -> `4 passed`.
- Final Knowledge full-stack live PostgreSQL: `KNOWLEDGE_FULLSTACK_TEST_DATABASE_URL=... uv run pytest tests/knowledge/test_fullstack_integration_live_postgres.py -q` -> `6 passed`.
- Final Microsoft Edge smoke against local Gateway + Next dev in production Knowledge mode: UI submitted `/mnt/user-data/uploads/edge-final-smoke.txt`, Gateway returned `202`, durable worker completed the job, Sources and Activity showed persisted production data, and Search returned cited ingested evidence through `/api/knowledge/search`.
- Final frontend suite: `npx pnpm@10.26.2 test` -> `339 passed`; `npx pnpm@10.26.2 typecheck` -> passed; `npx pnpm@10.26.2 lint` -> passed.
- Final production build: `NEXT_PUBLIC_KNOWLEDGE_DEMO_MODE=false npx pnpm@10.26.2 build` -> passed with the existing Turbopack NFT trace warning.
- Final demo/static build: `NEXT_PUBLIC_STATIC_WEBSITE_ONLY=true NEXT_PUBLIC_KNOWLEDGE_DEMO_MODE=true npx pnpm@10.26.2 build` -> passed with the existing Turbopack NFT trace warning.
- Final backend suite: `uv run pytest tests/knowledge -q` -> `112 passed, 16 skipped`; `make lint` -> passed; `make test` -> `4555 passed, 32 skipped`.

## Remaining Gaps

The remaining gaps are product/API scope, not external service requirements. Real Gmail, Calendar, third-party task systems, and model-backed external actions are still not connected. See `frontend-backend-contract-gaps.md` for the detailed contract table.

Next stage: Evaluation / Security / E2E Hardening. All action dispatch in this stage still uses deterministic fake adapters; real Gmail, Calendar, task, and external export connectors remain future scope.
