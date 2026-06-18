import type { z } from "zod";

import type { KnowledgeTransport } from "./types";
import {
  knowledgeJobAcceptedSchema,
  knowledgeJobSchema,
  unknownListEnvelopeSchema,
  unknownRecordSchema,
  type ActionPreviewInput,
  type AnalysisCreateInput,
  type ApprovalDecisionInput,
  type IngestionCreateInput,
  type KnowledgeUpdateReportInput,
  type KnowledgeClient,
  type KnowledgeRequestOptions,
  type ListParams,
  type RevisionCompareInput,
  type SearchInput,
  type WorkflowCreateInput,
} from "./types";

const trustedClientFields = new Set([
  "workspace_id",
  "user_id",
  "thread_id",
  "actor_id",
  "_trusted_user_id",
  "_trusted_actor_id",
  "_trusted_thread_id",
  "_trusted_storage_root",
]);

function assertNoTrustedFields(value: Record<string, unknown>) {
  for (const key of Object.keys(value)) {
    if (trustedClientFields.has(key)) {
      throw new Error(`Client payload cannot include trusted field: ${key}`);
    }
  }
}

function parseResponse<TSchema extends z.ZodTypeAny>(
  schema: TSchema,
  value: unknown,
): z.infer<TSchema> {
  return schema.parse(value);
}

function listQuery(params?: ListParams) {
  return {
    limit: params?.limit,
    offset: params?.offset,
  };
}

export function createKnowledgeClient(
  transport: KnowledgeTransport,
): KnowledgeClient {
  const client: KnowledgeClient = {
    async createIngestion(input: IngestionCreateInput, options) {
      assertNoTrustedFields(input as Record<string, unknown>);
      return parseResponse(
        knowledgeJobAcceptedSchema,
        await transport.request({
          method: "POST",
          path: "/ingestions",
          body: {
            source_type: input.source_type,
            source_uri: input.source_uri,
            media_type: input.media_type ?? null,
            metadata: input.metadata ?? {},
            idempotency_key: input.idempotency_key ?? null,
          },
          ...options,
        }),
      );
    },
    async getIngestion(jobId: string, options?: KnowledgeRequestOptions) {
      return client.getJob(jobId, options);
    },
    async retryIngestion(jobId: string, options?: KnowledgeRequestOptions) {
      return parseResponse(
        knowledgeJobAcceptedSchema,
        await transport.request({
          method: "POST",
          path: `/ingestions/${encodeURIComponent(jobId)}/retry`,
          ...options,
        }),
      );
    },
    async cancelIngestion(jobId: string, options?: KnowledgeRequestOptions) {
      return parseResponse(
        knowledgeJobAcceptedSchema,
        await transport.request({
          method: "POST",
          path: `/ingestions/${encodeURIComponent(jobId)}/cancel`,
          ...options,
        }),
      );
    },
    async getJob(jobId: string, options?: KnowledgeRequestOptions) {
      return parseResponse(
        knowledgeJobSchema,
        await transport.request({
          method: "GET",
          path: `/jobs/${encodeURIComponent(jobId)}`,
          ...options,
        }),
      );
    },
    async cancelJob(jobId: string, options?: KnowledgeRequestOptions) {
      return client.cancelIngestion(jobId, options);
    },
    async retryJob(jobId: string, options?: KnowledgeRequestOptions) {
      return client.retryIngestion(jobId, options);
    },
    async listActivity(params, options) {
      return parseResponse(
        unknownListEnvelopeSchema,
        await transport.request({
          method: "GET",
          path: "/activity",
          query: listQuery(params),
          ...options,
        }),
      );
    },
    async getOverview(options) {
      return parseResponse(
        unknownRecordSchema,
        await transport.request({
          method: "GET",
          path: "/overview",
          ...options,
        }),
      );
    },
    async listSources(params, options) {
      return parseResponse(
        unknownListEnvelopeSchema,
        await transport.request({
          method: "GET",
          path: "/sources",
          query: listQuery(params),
          ...options,
        }),
      );
    },
    async getSourceDetail(sourceId, options) {
      return parseResponse(
        unknownRecordSchema,
        await transport.request({
          method: "GET",
          path: `/sources/${encodeURIComponent(sourceId)}/detail`,
          ...options,
        }),
      );
    },
    async getSource(sourceId, options) {
      return parseResponse(
        unknownRecordSchema,
        await transport.request({
          method: "GET",
          path: `/sources/${encodeURIComponent(sourceId)}`,
          ...options,
        }),
      );
    },
    async listSourceRevisions(sourceId, params, options) {
      return parseResponse(
        unknownListEnvelopeSchema,
        await transport.request({
          method: "GET",
          path: `/sources/${encodeURIComponent(sourceId)}/revisions`,
          query: listQuery(params),
          ...options,
        }),
      );
    },
    async getRevision(revisionId, options) {
      return parseResponse(
        unknownRecordSchema,
        await transport.request({
          method: "GET",
          path: `/revisions/${encodeURIComponent(revisionId)}`,
          ...options,
        }),
      );
    },
    async compareRevisions(input: RevisionCompareInput, options) {
      return parseResponse(
        unknownRecordSchema,
        await transport.request({
          method: "POST",
          path: "/revisions/compare",
          body: input,
          ...options,
        }),
      );
    },
    async generateUpdateReport(input: KnowledgeUpdateReportInput, options) {
      return parseResponse(
        unknownRecordSchema,
        await transport.request({
          method: "POST",
          path: "/update-reports",
          body: {
            old_revision_id: input.old_revision_id ?? null,
            new_revision_id: input.new_revision_id,
          },
          ...options,
        }),
      );
    },
    async listClaims(params, options) {
      return parseResponse(
        unknownRecordSchema,
        await transport.request({
          method: "GET",
          path: "/claims",
          query: listQuery(params),
          ...options,
        }),
      );
    },
    async listConflicts(params, options) {
      return parseResponse(
        unknownRecordSchema,
        await transport.request({
          method: "GET",
          path: "/conflicts",
          query: listQuery(params),
          ...options,
        }),
      );
    },
    async getConflict(conflictId, options) {
      return parseResponse(
        unknownRecordSchema,
        await transport.request({
          method: "GET",
          path: `/conflicts/${encodeURIComponent(conflictId)}`,
          ...options,
        }),
      );
    },
    async search(input: SearchInput, options) {
      return parseResponse(
        unknownRecordSchema,
        await transport.request({
          method: "POST",
          path: "/search",
          body: {
            query: input.query,
            filters: input.filters ?? {},
            context_budget: input.context_budget ?? 4000,
          },
          ...options,
        }),
      );
    },
    async createAnalysis(input: AnalysisCreateInput, options) {
      assertNoTrustedFields(input as Record<string, unknown>);
      return parseResponse(
        unknownRecordSchema,
        await transport.request({
          method: "POST",
          path: "/analyses",
          body: {
            query: input.query,
            filters: input.filters ?? {},
            context_budget: input.context_budget ?? 4000,
            idempotency_key: input.idempotency_key ?? null,
          },
          ...options,
        }),
      );
    },
    async createWorkflow(input: WorkflowCreateInput, options) {
      assertNoTrustedFields(input.input ?? {});
      const raw = await transport.request({
        method: "POST",
        path: "/workflows",
        body: {
          workflow_type: input.workflow_type,
          input: input.input ?? {},
          idempotency_key: input.idempotency_key ?? null,
        },
        ...options,
      });
      const accepted = knowledgeJobAcceptedSchema.safeParse(raw);
      return accepted.success ? accepted.data : parseResponse(unknownRecordSchema, raw);
    },
    async listWorkflows(params, options) {
      return parseResponse(
        unknownListEnvelopeSchema,
        await transport.request({
          method: "GET",
          path: "/workflows",
          query: listQuery(params),
          ...options,
        }),
      );
    },
    async getWorkflow(workflowRunId, options) {
      return parseResponse(
        unknownRecordSchema,
        await transport.request({
          method: "GET",
          path: `/workflows/${encodeURIComponent(workflowRunId)}`,
          ...options,
        }),
      );
    },
    async advanceWorkflow(workflowRunId, options) {
      return parseResponse(
        knowledgeJobAcceptedSchema,
        await transport.request({
          method: "POST",
          path: `/workflows/${encodeURIComponent(workflowRunId)}/advance`,
          ...options,
        }),
      );
    },
    async listArtifacts(params, options) {
      return parseResponse(
        unknownListEnvelopeSchema,
        await transport.request({
          method: "GET",
          path: "/artifacts",
          query: listQuery(params),
          ...options,
        }),
      );
    },
    async getArtifact(artifactId, options) {
      return parseResponse(
        unknownRecordSchema,
        await transport.request({
          method: "GET",
          path: `/artifacts/${encodeURIComponent(artifactId)}`,
          ...options,
        }),
      );
    },
    async listApprovals(params, options) {
      return parseResponse(
        unknownListEnvelopeSchema,
        await transport.request({
          method: "GET",
          path: "/approvals",
          query: listQuery(params),
          ...options,
        }),
      );
    },
    async getApproval(approvalId, options) {
      return parseResponse(
        unknownRecordSchema,
        await transport.request({
          method: "GET",
          path: `/approvals/${encodeURIComponent(approvalId)}`,
          ...options,
        }),
      );
    },
    async decideApproval(approvalId, input: ApprovalDecisionInput, options) {
      return parseResponse(
        unknownRecordSchema,
        await transport.request({
          method: "POST",
          path: `/approvals/${encodeURIComponent(approvalId)}/decision`,
          body: input,
          ...options,
        }),
      );
    },
    async previewAction(approvalId, input: ActionPreviewInput, options) {
      return parseResponse(
        unknownRecordSchema,
        await transport.request({
          method: "POST",
          path: `/actions/${encodeURIComponent(approvalId)}/preview`,
          body: { action_draft: input.action_draft ?? {} },
          ...options,
        }),
      );
    },
    async executeAction(approvalId, options) {
      return parseResponse(
        unknownRecordSchema,
        await transport.request({
          method: "POST",
          path: `/actions/${encodeURIComponent(approvalId)}/execute`,
          ...options,
        }),
      );
    },
  };
  return client;
}
