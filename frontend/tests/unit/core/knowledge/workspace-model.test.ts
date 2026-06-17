import { describe, expect, test } from "vitest";

import {
  buildDemoImportPayload,
  filterSources,
  getDemoKnowledgeWorkspace,
  hasTrustedIdentityField,
  overviewStats,
  searchKnowledge,
  workflowTypeLabels,
} from "@/core/knowledge/workspace-model";

describe("Knowledge workspace model", () => {
  test("keeps demo fixtures cross-page consistent", () => {
    const dataset = getDemoKnowledgeWorkspace();
    const sourceIds = new Set(dataset.sources.map((source) => source.id));
    const revisionIds = new Set(
      dataset.sources.flatMap((source) =>
        source.revisions.map((revision) => revision.id),
      ),
    );
    for (const citation of dataset.citations) {
      expect(sourceIds.has(citation.sourceId)).toBe(true);
      expect(revisionIds.has(citation.revisionId)).toBe(true);
    }
    for (const claim of dataset.claims) {
      expect(claim.citationIds.every((id) => dataset.citations.some((citation) => citation.citationId === id))).toBe(true);
    }
    for (const conflict of dataset.conflicts) {
      expect(conflict.claimIds.every((id) => dataset.claims.some((claim) => claim.id === id))).toBe(true);
    }
  });

  test("computes overview stats without production-only assumptions", () => {
    const stats = overviewStats(getDemoKnowledgeWorkspace());
    expect(stats.sources).toBeGreaterThanOrEqual(4);
    expect(stats.claims).toBeGreaterThan(0);
    expect(stats.approvals).toBe(1);
    expect(stats.failedJobs).toBe(1);
  });

  test("filters sources by query type and status", () => {
    const dataset = getDemoKnowledgeWorkspace();
    const results = filterSources(dataset.sources, "climate", "pdf", "ACTIVE");
    expect(results).toHaveLength(1);
    expect(results[0]?.id).toBe("src-climate-brief");
    expect(filterSources(dataset.sources, "missing", "all", "all")).toEqual([]);
  });

  test("searches deterministic evidence results", () => {
    const dataset = getDemoKnowledgeWorkspace();
    expect(searchKnowledge(dataset, "staffing")[0]?.id).toBe("result-staffing");
    expect(searchKnowledge(dataset, "")).toHaveLength(dataset.searchResults.length);
  });

  test("builds ingestion payloads without trusted identity fields", () => {
    const payload = buildDemoImportPayload({
      mode: "url",
      sourceUri: "https://example.com/research",
      title: "Research",
    });
    expect(payload).toMatchObject({
      source_type: "url",
      source_uri: "https://example.com/research",
    });
    expect(hasTrustedIdentityField(payload)).toBe(false);
    expect(hasTrustedIdentityField({ workspace_id: "forged" })).toBe(true);
  });

  test("includes all seven workflow type labels", () => {
    expect(Object.keys(workflowTypeLabels)).toEqual([
      "topic_dossier",
      "project_context_pack",
      "reading_synthesis",
      "decision_memo",
      "meeting_preparation",
      "knowledge_update_review",
      "knowledge_to_action",
    ]);
  });

  test("does not confuse approved approvals with succeeded executions", () => {
    const dataset = getDemoKnowledgeWorkspace();
    const reconciliation = dataset.approvals.find(
      (approval) => approval.executionStatus === "RECONCILIATION_REQUIRED",
    );
    expect(reconciliation).toMatchObject({
      status: "APPROVED",
      executionStatus: "RECONCILIATION_REQUIRED",
    });
    const pending = dataset.approvals.find(
      (approval) => approval.status === "AWAITING_APPROVAL",
    );
    expect(pending?.executionStatus).toBe("PENDING");
  });
});
