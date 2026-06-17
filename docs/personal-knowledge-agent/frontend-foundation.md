# Personal Knowledge Agent Frontend Foundation

## Scope

This stage adds the frontend integration foundation for the completed Gateway Knowledge API. It does not add business pages for Sources, Search, Graph, Workflows, Approvals, or Artifacts.

## Runtime Wiring

- `KnowledgeProvider` is mounted under the existing workspace `AuthProvider` and `QueryClientProvider`.
- Production mode uses `GatewayKnowledgeTransport` against the existing Gateway proxy/base URL.
- Demo mode uses `DemoKnowledgeTransport` and deterministic fixtures, with no network calls.
- Knowledge query cache entries live under the `["knowledge"]` key and are cleared when the authenticated user changes.

## Public Configuration

Only browser-safe public variables are exposed:

- `NEXT_PUBLIC_KNOWLEDGE_API_BASE_PATH`
- `NEXT_PUBLIC_KNOWLEDGE_DEMO_MODE`
- `NEXT_PUBLIC_KNOWLEDGE_REQUEST_TIMEOUT_MS`
- `NEXT_PUBLIC_KNOWLEDGE_SSE_INITIAL_RETRY_MS`
- `NEXT_PUBLIC_KNOWLEDGE_SSE_MAX_RETRY_MS`
- `NEXT_PUBLIC_KNOWLEDGE_SSE_MAX_RETRIES`

Server secrets, database URLs, tokens, and trusted workspace/user identity are not part of the frontend configuration.

## API Client

The client maps to the real backend routes under `/api/knowledge`:

- ingestion job create/status/retry/cancel
- generic job status
- activity, sources, source revisions, claims, conflicts
- search, analysis, workflow, artifact, approval, action preview/execute

Client request payloads reject trusted identity fields such as `workspace_id`, `user_id`, `thread_id`, and `actor_id`. Workspace identity remains derived by Gateway trusted auth dependencies.

## CSRF And Auth

State-changing requests include the existing CSRF cookie value through `X-CSRF-Token` and always use `credentials: "include"`. The Knowledge transport normalizes errors locally instead of using the generic fetch wrapper that redirects on `401`, so Knowledge views can render explicit auth/configuration states.

## SSE Lifecycle

`subscribeKnowledgeJobEvents` consumes the Gateway job event stream with fetch streaming:

- sends cookies with `credentials: "include"`
- resumes with `after_seq`
- sends `Last-Event-ID` when a cursor exists
- ignores heartbeat comments
- deduplicates events at or below the cursor
- closes on `job_succeeded`, `job_failed`, and `job_cancelled`
- uses bounded exponential retry
- stops retrying on authentication, authorization, CSRF, and not-found failures

## Error Model

`KnowledgeApiError` classifies network, timeout, authentication, authorization, CSRF, validation, not-found, conflict, rate-limit, server, service-unavailable, job-failed, job-cancelled, and unknown errors. Request IDs are preserved when the Gateway returns them.

## Current Backend Capability Boundaries

The foundation intentionally lists these as missing backend capabilities instead of pretending they are executable routes:

- graph expansion
- revision comparison
- knowledge update report
- workflow artifact generation
- artifact/provenance/workflow/approval validation endpoints

## Tests

Focused unit coverage lives in `frontend/tests/unit/core/knowledge/` for config resolution, transport request shape, client validation, error normalization, demo fixtures, SSE parsing/closing, and query helper behavior.
