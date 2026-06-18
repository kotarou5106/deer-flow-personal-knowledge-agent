# Frontend Backend Contract Gaps

The Knowledge Workspace UI only calls or models formal Gateway contracts. The read-model, ingestion/search, workflow, and artifact vertical slices are now Gateway-backed in production mode. Demo data still fills the full visual workspace, while production mode keeps the following incomplete surfaces conservative.

## Completed In This Integration Stage

- `GET /api/knowledge/overview`
- `GET /api/knowledge/sources`
- `GET /api/knowledge/sources/{source_id}/detail`
- `GET /api/knowledge/activity` as a jobs/source activity surface
- `POST /api/knowledge/ingestions`
- `GET /api/knowledge/jobs/{job_id}`
- `GET /api/knowledge/jobs/{job_id}/events`
- `POST /api/knowledge/search` for retrieved chunks with provenance-backed citations
- `GET /api/knowledge/workflows`
- `POST /api/knowledge/workflows`
- `GET /api/knowledge/workflows/{workflow_run_id}`
- `POST /api/knowledge/workflows/{workflow_run_id}/advance`
- `POST /api/knowledge/workflows/{workflow_run_id}/pause`
- `POST /api/knowledge/workflows/{workflow_run_id}/resume`
- `POST /api/knowledge/workflows/{workflow_run_id}/retry`
- `GET /api/knowledge/artifacts`
- `POST /api/knowledge/workflows/{workflow_run_id}/artifacts`
- `GET /api/knowledge/artifacts/{artifact_id}`
- `GET /api/knowledge/artifacts/{artifact_id}/evidence-links`

## Workflow / Artifact Status

Production Workflow UI now calls the formal Gateway contracts for create, advance, pause, resume, retry, and artifact generation. Gateway executes these through the database-backed deterministic workflow engine, not durable fake job fallbacks. Workflow responses include steps, artifact IDs, trusted input, timestamps, and errors.

Artifact detail now includes markdown preview text, workflow origin, staleness/validation state, and evidence links. Evidence links include artifact-evidence link IDs plus source, revision, chunk, evidence span, and claim provenance where available.

Knowledge-to-Action is intentionally draft-only in this stage. It can create a non-executed action draft, but approval routing and action execution remain out of scope.

| Page | Needed Capability | Existing Domain Service / Tool | Missing Gateway Endpoint | Suggested Contract | Priority |
| --- | --- | --- | --- | --- | --- |
| Revisions | Revision diff by old/new revision | `updates.revision_diff` | `GET /api/knowledge/revisions/diff?old_revision_id=&new_revision_id=` | `{summary, items:[{change_type, old_chunk, new_chunk, summary}]}` | High |
| Search | Related entity and claim metadata for retrieved chunks | retrieval service | Extend `POST /api/knowledge/search` response schema | `{results:[{snippet,citations,retrieval_channels,related_entities,related_claims}]}` | Medium |
| Analysis | Fetch completed structured analysis result | analysis service and analysis job route | `GET /api/knowledge/analyses/{job_id}/result` | `AnalysisResult` schema from backend analysis module | High |
| Graph | Entity/claim/source/evidence graph and neighbor expansion | retrieval graph module | `GET /api/knowledge/graph`, `GET /api/knowledge/graph/nodes/{id}/neighbors` | `{nodes, edges, cursors, truncated}` | Medium |
| Conflicts | Conflict detail, affected artifacts, and recommended next step | updates conflict detector | Extend `GET /api/knowledge/conflicts` and add `GET /api/knowledge/conflicts/{id}` | `{classification,status,claims,citations,affected_artifacts,recommended_next_step}` | High |
| Conflicts | Resolve or annotate conflict | no formal mutation exposed | `POST /api/knowledge/conflicts/{id}/decision` | `{decision, rationale}` with audit record | Medium |
| Workflows | Per-step partial execution controls and manual parameter edits | workflow engine | No formal endpoint | Future mutation contract for a specific step run | Low |
| Artifacts | Download/export formats beyond markdown preview and stored JSON payload | artifact storage service | Dedicated download/export route | File response or signed project-owned download URL | Medium |
| Approvals | Payload invalidation visibility | approval/action services | Extend approval detail | `{payload_hash,current_payload_hash,is_payload_stale}` | High |
| Approvals | Execution reconciliation status detail | action execution model | Extend action execute/detail response | `{execution_status,result,audit,reconciliation_required_reason}` | High |
| Activity | Unified audit/activity log beyond source/job events | audit model exists; activity route currently jobs/source-focused | Extend `GET /api/knowledge/activity` or add `GET /api/knowledge/audit` | cursor-paginated events with safe summaries | Medium |

Next stage: add the remaining contracts in focused backend slices and then switch the corresponding production UI panels from unavailable/partial to Gateway-backed data.
