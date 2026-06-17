# Knowledge Workspace UI

## Scope

This stage adds a complete, demo-ready Personal Knowledge Agent workspace in the existing DeerFlow workspace shell. It builds on the Frontend Foundation and does not reimplement Gateway, auth, CSRF, durable jobs, or backend domain services.

## Routes

- `/workspace/knowledge`
- `/workspace/knowledge/sources`
- `/workspace/knowledge/sources/[source_id]`
- `/workspace/knowledge/search`
- `/workspace/knowledge/analysis`
- `/workspace/knowledge/graph`
- `/workspace/knowledge/conflicts`
- `/workspace/knowledge/workflows`
- `/workspace/knowledge/artifacts`
- `/workspace/knowledge/approvals`
- `/workspace/knowledge/activity`

## Shared UI

All routes share:

- Knowledge side navigation
- page header and breadcrumb through the existing workspace layout
- Demo / Production mode badge
- service availability notice
- empty, loading, unavailable, and error-safe states
- citation detail sheet
- consistent status, risk, conflict, citation, and stale-state badges

## Demo Dataset

The deterministic demo dataset contains:

- multiple sources across PDF, Markdown, XLSX, and URL
- completed, running, and failed ingestion jobs
- two revisions and a revision diff
- chunks, entities, claims, relations, evidence spans, and parent context
- search results with Lexical, Vector, Graph, and Fused Result channels
- evidence-grounded analysis sections
- a graph using shared entity/claim/source IDs
- unresolved conflicts
- Decision Memo and Action Draft artifacts
- pending, succeeded, and reconciliation-required approval/action states
- activity events across ingestion, workflow, approval, and update categories

The demo transport and workspace UI use the same fixture source to avoid data drift. Demo mode does not call external services.

## Production Behavior

Production mode is intentionally conservative. It does not fabricate stats, graph data, revision diffs, unified audit events, or workflow artifacts from missing endpoints. Panels show unavailable states until formal Gateway contracts exist. Existing Gateway contracts remain the integration target for the next stage.

## Evidence Rules

- Supported facts show citations.
- Inferences are explicitly marked as inferred conclusions.
- Unsupported claims and unresolved questions are not rendered as facts.
- Parent context is visually labeled as context only and is not treated as direct evidence.
- Artifacts surface stale reasons and provenance links.

## Safety Rules

- UI never asks for or stores server secrets.
- Workspace identity remains derived from existing Auth Context and Gateway trusted auth.
- Import payload helpers do not include trusted identity fields.
- Knowledge-to-Action creates action drafts; execution remains approval-gated.
- Public demo actions are fake actions only.
