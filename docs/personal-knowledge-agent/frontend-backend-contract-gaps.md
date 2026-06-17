# Frontend Backend Contract Gaps

The Knowledge Workspace UI only calls or models formal Gateway contracts. Demo data fills the visual workspace, while production mode marks the following surfaces as unavailable until Gateway endpoints are added.

| Page | Needed Capability | Existing Domain Service / Tool | Missing Gateway Endpoint | Suggested Contract | Priority |
| --- | --- | --- | --- | --- | --- |
| Overview | Aggregate source, revision, job, claim, entity, relation, conflict, workflow, artifact, and approval counts | repositories and job service exist separately | `GET /api/knowledge/overview` | `{stats, recent_sources, running_jobs, recent_artifacts, pending_approvals}` | High |
| Source Detail | Source chunks, entities, claims, relations, evidence spans, and ingestion history in one payload | source, knowledge repositories, ingestion jobs | `GET /api/knowledge/sources/{source_id}/detail` | `{source, revisions, chunks, claims, relations, evidence, jobs}` | High |
| Revisions | Revision diff by old/new revision | `updates.revision_diff` | `GET /api/knowledge/revisions/diff?old_revision_id=&new_revision_id=` | `{summary, items:[{change_type, old_chunk, new_chunk, summary}]}` | High |
| Search | Structured retrieval channel metadata | retrieval service | Extend `POST /api/knowledge/search` response schema | `{results:[{snippet,citations,retrieval_channels,related_entities,related_claims}]}` | High |
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
| Activity | Unified audit/activity log | audit model exists; activity route currently jobs-only | `GET /api/knowledge/activity` extended or `GET /api/knowledge/audit` | cursor-paginated events with safe summaries | Medium |

Next stage: Frontend-Backend Integration should add these contracts in focused backend slices and then switch production UI panels from unavailable to Gateway-backed data.
