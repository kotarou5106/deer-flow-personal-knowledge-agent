# Frontend Backend Contract Gaps

The Knowledge Workspace UI only calls or models formal Gateway contracts. The read-model and ingestion/search vertical slice is now Gateway-backed in production mode. Demo data still fills the full visual workspace, while production mode keeps the following incomplete surfaces conservative.

## Completed In This Integration Stage

- `GET /api/knowledge/overview`
- `GET /api/knowledge/sources`
- `GET /api/knowledge/sources/{source_id}/detail`
- `GET /api/knowledge/activity` as a jobs/source activity surface
- `POST /api/knowledge/ingestions`
- `GET /api/knowledge/jobs/{job_id}`
- `GET /api/knowledge/jobs/{job_id}/events`
- `POST /api/knowledge/search` for retrieved chunks with provenance-backed citations

| Page | Needed Capability | Existing Domain Service / Tool | Missing Gateway Endpoint | Suggested Contract | Priority |
| --- | --- | --- | --- | --- | --- |
| Revisions | Revision diff by old/new revision | `updates.revision_diff` | `GET /api/knowledge/revisions/diff?old_revision_id=&new_revision_id=` | `{summary, items:[{change_type, old_chunk, new_chunk, summary}]}` | High |
| Search | Related entity and claim metadata for retrieved chunks | retrieval service | Extend `POST /api/knowledge/search` response schema | `{results:[{snippet,citations,retrieval_channels,related_entities,related_claims}]}` | Medium |
| Analysis | Fetch completed structured analysis result | analysis service and analysis job route | `GET /api/knowledge/analyses/{job_id}/result` | `AnalysisResult` schema from backend analysis module | High |
| Graph | Entity/claim/source/evidence graph and neighbor expansion | retrieval graph module | `GET /api/knowledge/graph`, `GET /api/knowledge/graph/nodes/{id}/neighbors` | `{nodes, edges, cursors, truncated}` | Medium |
| Conflicts | Conflict detail, affected artifacts, and recommended next step | updates conflict detector | Extend `GET /api/knowledge/conflicts` and add `GET /api/knowledge/conflicts/{id}` | `{classification,status,claims,citations,affected_artifacts,recommended_next_step}` | High |
| Conflicts | Resolve or annotate conflict | no formal mutation exposed | `POST /api/knowledge/conflicts/{id}/decision` | `{decision, rationale}` with audit record | Medium |
| Workflows | List workflow runs | workflow repository | `GET /api/knowledge/workflows` | `{data:[WorkflowRunSummary], pagination}` | High |
| Workflows | Pause workflow | workflow state machine may support state transitions, no Gateway route | `POST /api/knowledge/workflows/{id}/pause` | `{workflow_run_id,status,current_step}` | Medium |
| Workflows | Step timeline | workflow step repository | `GET /api/knowledge/workflows/{id}/steps` or include in detail | `{steps:[{key,sequence,status,input_summary,output_summary,error}]}` | High |
| Artifacts | Artifact content preview/download and provenance bundle | artifact service and repositories | Extend `GET /api/knowledge/artifacts/{id}` | `{artifact, markdown, evidence_links, workflow_origin, stale_reasons}` | High |
| Approvals | Payload invalidation visibility | approval/action services | Extend approval detail | `{payload_hash,current_payload_hash,is_payload_stale}` | High |
| Approvals | Execution reconciliation status detail | action execution model | Extend action execute/detail response | `{execution_status,result,audit,reconciliation_required_reason}` | High |
| Activity | Unified audit/activity log beyond source/job events | audit model exists; activity route currently jobs/source-focused | Extend `GET /api/knowledge/activity` or add `GET /api/knowledge/audit` | cursor-paginated events with safe summaries | Medium |

Next stage: add the remaining contracts in focused backend slices and then switch the corresponding production UI panels from unavailable/partial to Gateway-backed data.
