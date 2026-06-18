import { describe, expect, test } from "vitest";

import {
  buildDemoImportPayload,
  demoOverviewSummary,
  demoRecommendedPath,
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
    expect(stats.sources).toBe(4);
    expect(stats.claims).toBeGreaterThan(0);
    expect(stats.approvals).toBe(1);
    expect(stats.conflicts).toBe(2);
  });

  test("filters sources by query type and status", () => {
    const dataset = getDemoKnowledgeWorkspace();
    const results = filterSources(dataset.sources, "production-architecture", "markdown", "ACTIVE");
    expect(results).toHaveLength(1);
    expect(results[0]?.id).toBe("src-atlas-architecture");
    expect(filterSources(dataset.sources, "missing", "all", "all")).toEqual([]);
  });

  test("searches deterministic evidence results", () => {
    const dataset = getDemoKnowledgeWorkspace();
    expect(searchKnowledge(dataset, "生产数据库方案")[0]?.id).toBe("result-atlas-current-database");
    expect(searchKnowledge(dataset, "外部通知")[0]?.id).toBe("result-atlas-notification-policy");
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

  test("does not confuse pending approvals with succeeded fake executions", () => {
    const dataset = getDemoKnowledgeWorkspace();
    const executed = dataset.approvals.find(
      (approval) => approval.executionStatus === "SUCCEEDED",
    );
    expect(executed).toMatchObject({
      status: "APPROVED",
      executionStatus: "SUCCEEDED",
      payloadSummary: expect.stringContaining("Fake Action Adapter"),
    });
    const pending = dataset.approvals.find(
      (approval) => approval.status === "AWAITING_APPROVAL",
    );
    expect(pending?.executionStatus).toBe("PENDING");
  });

  test("uses one Project Atlas canonical demo story across pages", () => {
    const dataset = getDemoKnowledgeWorkspace();
    expect(dataset.sources.every((source) => source.title.includes("Project Atlas") || source.canonicalUri.includes(".md"))).toBe(true);

    const architecture = dataset.sources.find((source) => source.canonicalUri.endsWith("production-architecture.md"));
    expect(architecture?.revisions).toHaveLength(2);
    expect(architecture?.currentRevisionId).toBe("rev-atlas-architecture-2");
    expect(architecture?.diff.map((item) => item.summary)).toEqual([
      "移除：SQLite",
      "新增：PostgreSQL 16 + pgvector",
    ]);

    const currentRevision = architecture?.revisions.find((revision) => revision.id === architecture.currentRevisionId);
    expect(currentRevision?.chunks.map((chunk) => chunk.content).join("\n")).toContain("PostgreSQL 16 与 pgvector");

    const meetingNotes = dataset.sources.find((source) => source.canonicalUri.endsWith("architecture-meeting-notes.md"));
    expect(meetingNotes?.revisions[0]?.chunks[0]?.content).toContain("SQLite");
  });

  test("models both required conflict groups with real classifications", () => {
    const dataset = getDemoKnowledgeWorkspace();
    expect(dataset.conflicts).toHaveLength(2);
    expect(dataset.conflicts).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          id: "conflict-atlas-storage-update",
          classification: "TEMPORAL_UPDATE",
          summary: expect.stringContaining("数据库方案"),
        }),
        expect.objectContaining({
          id: "conflict-atlas-notification-approval",
          classification: "DIRECT_CONTRADICTION",
          summary: expect.stringContaining("外部通知"),
        }),
      ]),
    );
  });

  test("keeps search and analysis grounded in the current architecture revision", () => {
    const dataset = getDemoKnowledgeWorkspace();
    const result = searchKnowledge(dataset, "PostgreSQL 16")[0];
    expect(result).toMatchObject({
      sourceId: "src-atlas-architecture",
      revisionId: "rev-atlas-architecture-2",
    });
    expect(result?.citationIds).toContain("cite-architecture-v2-postgres");

    expect(dataset.analysis.supportedFacts[0]).toMatchObject({
      statement: "Project Atlas 当前生产架构采用 PostgreSQL 16 和 pgvector。",
      citationIds: ["cite-architecture-v2-postgres"],
    });
    expect(dataset.analysis.inferredConclusions[0]).toMatchObject({
      statement: expect.stringContaining("可能是为了支持"),
    });
    expect(dataset.analysis.unsupportedClaims[0]?.statement).toContain("大规模生产流量验证");
  });

  test("models current and stale artifacts with revision-aware stale reason", () => {
    const dataset = getDemoKnowledgeWorkspace();
    const current = dataset.artifacts.find((artifact) => artifact.stalenessStatus === "CURRENT");
    const stale = dataset.artifacts.find((artifact) => artifact.stalenessStatus === "STALE");
    expect(current).toMatchObject({
      title: "Project Atlas 生产存储决策备忘录",
      artifactType: "Decision Memo",
    });
    expect(stale).toMatchObject({
      title: "Project Atlas 初版存储决策备忘录",
      staleReasons: [expect.stringContaining("Revision 1 更新至 Revision 2")],
    });
  });

  test("models approval-gated action without real external side effects", () => {
    const dataset = getDemoKnowledgeWorkspace();
    const pending = dataset.approvals.find((approval) => approval.id === "approval-atlas-notification-email");
    expect(pending).toMatchObject({
      actionType: "EMAIL_DRAFT",
      status: "AWAITING_APPROVAL",
      executionStatus: "PENDING",
      payloadSummary: expect.stringContaining("PostgreSQL 16 + pgvector"),
    });
    expect(dataset.claims.find((claim) => claim.id === "claim-security-fake-adapter")?.text).toContain("不得发送真实邮件");
  });

  test("keeps overview summary and recommended path consistent with fixtures", () => {
    const dataset = getDemoKnowledgeWorkspace();
    expect(demoOverviewSummary(dataset).map((item) => [item.label, item.value])).toEqual([
      ["资料来源", dataset.sources.length],
      ["主要版本更新", 1],
      ["知识冲突", dataset.conflicts.length],
      ["正式产物", dataset.artifacts.length],
      ["待审批行动", 1],
    ]);
    expect(demoRecommendedPath.map((item) => item.href)).toEqual([
      "/workspace/knowledge/sources/src-atlas-architecture",
      "/workspace/knowledge/search",
      "/workspace/knowledge/analysis",
      "/workspace/knowledge/conflicts",
      "/workspace/knowledge/artifacts",
      "/workspace/knowledge/approvals",
    ]);
  });
});
