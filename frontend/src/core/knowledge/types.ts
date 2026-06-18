import { z } from "zod";

export const knowledgeJobStatusSchema = z.enum([
  "QUEUED",
  "RUNNING",
  "SUCCEEDED",
  "FAILED",
  "CANCEL_REQUESTED",
  "CANCELLED",
  "RETRY_SCHEDULED",
]);

export type KnowledgeJobStatus = z.infer<typeof knowledgeJobStatusSchema>;

export const terminalKnowledgeJobStatuses = new Set<KnowledgeJobStatus>([
  "SUCCEEDED",
  "FAILED",
  "CANCELLED",
]);

export const knowledgeJobAcceptedSchema = z.object({
  job_id: z.string(),
  status: knowledgeJobStatusSchema,
  status_url: z.string(),
  events_url: z.string(),
});

export type KnowledgeJobAccepted = z.infer<typeof knowledgeJobAcceptedSchema>;

export const knowledgeJobSchema = z.object({
  job_id: z.string(),
  workspace_id: z.string(),
  job_type: z.string(),
  status: knowledgeJobStatusSchema,
  payload_hash: z.string(),
  idempotency_key: z.string().nullable(),
  attempt: z.number(),
  max_attempts: z.number(),
  progress: z.record(z.unknown()),
  created_at: z.string(),
  started_at: z.string().nullable(),
  completed_at: z.string().nullable(),
  error_type: z.string().nullable(),
  error_message: z.string().nullable(),
  result_reference: z.record(z.unknown()).nullable(),
});

export type KnowledgeJob = z.infer<typeof knowledgeJobSchema>;

export const knowledgeJobEventSchema = z.object({
  event_id: z.string(),
  job_id: z.string(),
  seq: z.number(),
  event_type: z.string(),
  payload: z.record(z.unknown()),
  created_at: z.string(),
});

export type KnowledgeJobEvent = z.infer<typeof knowledgeJobEventSchema>;

export const paginationSchema = z.object({
  limit: z.number(),
  offset: z.number(),
});

export const unknownRecordSchema = z.record(z.unknown());

export const unknownListEnvelopeSchema = z.object({
  data: z.array(unknownRecordSchema),
  pagination: paginationSchema.optional(),
});

export type UnknownListEnvelope = z.infer<typeof unknownListEnvelopeSchema>;

export type IngestionCreateInput = {
  source_type: "file" | "url" | "text";
  source_uri: string;
  media_type?: string | null;
  metadata?: Record<string, unknown>;
  idempotency_key?: string | null;
};

export type SearchInput = {
  query: string;
  filters?: Record<string, unknown>;
  context_budget?: number;
};

export type AnalysisCreateInput = {
  query: string;
  filters?: Record<string, unknown>;
  context_budget?: number;
  idempotency_key?: string | null;
};

export type RevisionCompareInput = {
  old_revision_id: string;
  new_revision_id: string;
};

export type KnowledgeUpdateReportInput = {
  old_revision_id?: string | null;
  new_revision_id: string;
};

export type WorkflowCreateInput = {
  workflow_type: string;
  input?: Record<string, unknown>;
  idempotency_key?: string | null;
};

export type ApprovalDecisionInput = {
  decision: "approve" | "reject" | "cancel";
  reason?: string | null;
};

export type ActionPreviewInput = {
  action_draft?: Record<string, unknown>;
};

export type ListParams = {
  limit?: number;
  offset?: number;
};

export type KnowledgeClient = {
  createIngestion: (
    input: IngestionCreateInput,
    options?: KnowledgeRequestOptions,
  ) => Promise<KnowledgeJobAccepted>;
  getIngestion: (
    jobId: string,
    options?: KnowledgeRequestOptions,
  ) => Promise<KnowledgeJob>;
  retryIngestion: (
    jobId: string,
    options?: KnowledgeRequestOptions,
  ) => Promise<KnowledgeJobAccepted>;
  cancelIngestion: (
    jobId: string,
    options?: KnowledgeRequestOptions,
  ) => Promise<KnowledgeJobAccepted>;
  getJob: (
    jobId: string,
    options?: KnowledgeRequestOptions,
  ) => Promise<KnowledgeJob>;
  cancelJob: (
    jobId: string,
    options?: KnowledgeRequestOptions,
  ) => Promise<KnowledgeJobAccepted>;
  retryJob: (
    jobId: string,
    options?: KnowledgeRequestOptions,
  ) => Promise<KnowledgeJobAccepted>;
  listActivity: (
    params?: ListParams,
    options?: KnowledgeRequestOptions,
  ) => Promise<UnknownListEnvelope>;
  getOverview: (
    options?: KnowledgeRequestOptions,
  ) => Promise<Record<string, unknown>>;
  listSources: (
    params?: ListParams,
    options?: KnowledgeRequestOptions,
  ) => Promise<UnknownListEnvelope>;
  getSource: (
    sourceId: string,
    options?: KnowledgeRequestOptions,
  ) => Promise<Record<string, unknown>>;
  listSourceRevisions: (
    sourceId: string,
    params?: ListParams,
    options?: KnowledgeRequestOptions,
  ) => Promise<UnknownListEnvelope>;
  getSourceDetail: (
    sourceId: string,
    options?: KnowledgeRequestOptions,
  ) => Promise<Record<string, unknown>>;
  getRevision: (
    revisionId: string,
    options?: KnowledgeRequestOptions,
  ) => Promise<Record<string, unknown>>;
  compareRevisions: (
    input: RevisionCompareInput,
    options?: KnowledgeRequestOptions,
  ) => Promise<Record<string, unknown>>;
  generateUpdateReport: (
    input: KnowledgeUpdateReportInput,
    options?: KnowledgeRequestOptions,
  ) => Promise<Record<string, unknown>>;
  listClaims: (
    params?: ListParams,
    options?: KnowledgeRequestOptions,
  ) => Promise<Record<string, unknown>>;
  listConflicts: (
    params?: ListParams,
    options?: KnowledgeRequestOptions,
  ) => Promise<Record<string, unknown>>;
  getConflict: (
    conflictId: string,
    options?: KnowledgeRequestOptions,
  ) => Promise<Record<string, unknown>>;
  search: (
    input: SearchInput,
    options?: KnowledgeRequestOptions,
  ) => Promise<Record<string, unknown>>;
  createAnalysis: (
    input: AnalysisCreateInput,
    options?: KnowledgeRequestOptions,
  ) => Promise<Record<string, unknown>>;
  createWorkflow: (
    input: WorkflowCreateInput,
    options?: KnowledgeRequestOptions,
  ) => Promise<KnowledgeJobAccepted | Record<string, unknown>>;
  listWorkflows: (
    params?: ListParams,
    options?: KnowledgeRequestOptions,
  ) => Promise<UnknownListEnvelope>;
  getWorkflow: (
    workflowRunId: string,
    options?: KnowledgeRequestOptions,
  ) => Promise<Record<string, unknown>>;
  advanceWorkflow: (
    workflowRunId: string,
    options?: KnowledgeRequestOptions,
  ) => Promise<KnowledgeJobAccepted>;
  listArtifacts: (
    params?: ListParams,
    options?: KnowledgeRequestOptions,
  ) => Promise<UnknownListEnvelope>;
  getArtifact: (
    artifactId: string,
    options?: KnowledgeRequestOptions,
  ) => Promise<Record<string, unknown>>;
  listApprovals: (
    params?: ListParams,
    options?: KnowledgeRequestOptions,
  ) => Promise<UnknownListEnvelope>;
  getApproval: (
    approvalId: string,
    options?: KnowledgeRequestOptions,
  ) => Promise<Record<string, unknown>>;
  decideApproval: (
    approvalId: string,
    input: ApprovalDecisionInput,
    options?: KnowledgeRequestOptions,
  ) => Promise<Record<string, unknown>>;
  previewAction: (
    approvalId: string,
    input: ActionPreviewInput,
    options?: KnowledgeRequestOptions,
  ) => Promise<Record<string, unknown>>;
  executeAction: (
    approvalId: string,
    options?: KnowledgeRequestOptions,
  ) => Promise<Record<string, unknown>>;
};

export type KnowledgeRequestOptions = {
  signal?: AbortSignal;
  timeoutMs?: number;
};

export type KnowledgeTransportRequest = {
  method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  path: string;
  query?: Record<string, string | number | boolean | null | undefined>;
  body?: unknown;
  signal?: AbortSignal;
  timeoutMs?: number;
};

export type KnowledgeTransport = {
  request: (request: KnowledgeTransportRequest) => Promise<unknown>;
};

export type MissingKnowledgeCapability =
  | "graph_expansion"
  | "revision_comparison"
  | "knowledge_update_report"
  | "workflow_artifact_generation"
  | "artifact_validation"
  | "provenance_validation"
  | "workflow_validation"
  | "approval_validation";

export const missingBackendCapabilities: MissingKnowledgeCapability[] = [
  "graph_expansion",
  "workflow_artifact_generation",
  "artifact_validation",
  "provenance_validation",
  "workflow_validation",
  "approval_validation",
];
