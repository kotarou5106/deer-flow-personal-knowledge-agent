# Knowledge Full-Stack Integration

Last updated: 2026-06-18

This stage connects the Knowledge Workspace production UI to the project-owned Gateway and Knowledge APIs. It does not require OpenAI, Anthropic, Tavily, Firecrawl, DeepSeek, or any other external model/API service. Verification used fake/deterministic/local providers plus a temporary local pgvector PostgreSQL container.

## Completed Vertical Slice

- `POST /api/knowledge/ingestions` accepts browser file imports without trusted identity fields.
- Gateway derives trusted user, actor, thread, workspace, and storage root server-side.
- Gateway durable worker processes local file and URL jobs.
- `GET /api/knowledge/jobs/{job_id}/events` streams monotonic SSE events through terminal states.
- `GET /api/knowledge/sources`, `/overview`, and `/sources/{source_id}/detail` expose live source, revision, chunk, and job data.
- `POST /api/knowledge/search` returns retrieved chunks with provenance; the frontend maps those into citations.
- Workspace isolation is verified with separate trusted owner contexts.
- URL ingestion verifies SSRF rejection for blocked localhost URLs and a monkeypatched localhost-only happy path inside tests.

## Frontend Runtime Fixes

- Production Knowledge read surfaces now load after browser hydration instead of caching server-side relative-fetch failures.
- Gateway transport binds `globalThis.fetch` so Chromium/Edge do not raise `Illegal invocation`.
- File import media type is inferred from the URI extension instead of hardcoding PDF.
- Production search maps real retrieved chunk provenance into citation drawer data.
- Error normalization preserves ordinary JavaScript error messages to keep local diagnostics actionable.

## Verification

- `uv run ruff check app/gateway/deps.py packages/harness/deerflow/knowledge/runtime/provider.py tests/knowledge/test_fullstack_integration_live_postgres.py`
- `uv run pytest tests/knowledge/test_gateway_jobs.py -q`
- `KNOWLEDGE_FULLSTACK_TEST_DATABASE_URL=... uv run pytest tests/knowledge/test_fullstack_integration_live_postgres.py -q`
- `uv run pytest tests/knowledge -q`
- `npx pnpm@10.26.2 test`
- `npx pnpm@10.26.2 typecheck`
- `npx pnpm@10.26.2 lint`
- `NEXT_PUBLIC_KNOWLEDGE_DEMO_MODE=false npx pnpm@10.26.2 build`
- Microsoft Edge smoke against local Gateway + Next dev: UI import accepted, job succeeded, source appeared, search returned the ingested evidence.

## Remaining Gaps

The remaining gaps are product/API scope, not external service requirements. See `frontend-backend-contract-gaps.md` for the detailed contract table.
