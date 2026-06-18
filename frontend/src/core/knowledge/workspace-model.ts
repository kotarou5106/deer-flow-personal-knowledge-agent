import type { KnowledgeJobAccepted } from "./types";
import { demoKnowledgeWorkspace } from "./workspace-fixtures";
import type {
  DemoImportResult,
  KnowledgeActivityEvent,
  KnowledgeArtifact,
  KnowledgeClaim,
  KnowledgeConflict,
  KnowledgeImportDraft,
  KnowledgeSource,
  KnowledgeWorkspaceDataset,
  WorkflowType,
} from "./workspace-types";

export const knowledgeRoutes = [
  { href: "/workspace/knowledge", label: "概览" },
  { href: "/workspace/knowledge/sources", label: "来源" },
  { href: "/workspace/knowledge/search", label: "检索" },
  { href: "/workspace/knowledge/analysis", label: "分析" },
  { href: "/workspace/knowledge/graph", label: "图谱" },
  { href: "/workspace/knowledge/conflicts", label: "冲突" },
  { href: "/workspace/knowledge/workflows", label: "工作流" },
  { href: "/workspace/knowledge/artifacts", label: "产物" },
  { href: "/workspace/knowledge/approvals", label: "审批" },
  { href: "/workspace/knowledge/activity", label: "活动" },
] as const;

export const workflowTypeLabels: Record<WorkflowType, string> = {
  topic_dossier: "Topic Dossier",
  project_context_pack: "Project Context Pack",
  reading_synthesis: "Reading Synthesis",
  decision_memo: "Decision Memo",
  meeting_preparation: "Meeting Preparation",
  knowledge_update_review: "Knowledge Update Review",
  knowledge_to_action: "Knowledge-to-Action",
};

export const demoRecommendedPath = [
  { label: "查看架构方案的新旧版本", href: "/workspace/knowledge/sources/src-atlas-architecture" },
  { label: "检索当前数据库决策", href: "/workspace/knowledge/search" },
  { label: "查看证据化分析", href: "/workspace/knowledge/analysis" },
  { label: "检查两组知识冲突", href: "/workspace/knowledge/conflicts" },
  { label: "打开决策备忘录", href: "/workspace/knowledge/artifacts" },
  { label: "查看待审批行动", href: "/workspace/knowledge/approvals" },
] as const;

export function getDemoKnowledgeWorkspace(): KnowledgeWorkspaceDataset {
  return demoKnowledgeWorkspace;
}

export function formatKnowledgeDate(value: string | null | undefined): string {
  if (!value) return "Not yet";
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

export function formatKnowledgeCount(value: number, label: string): string {
  return `${new Intl.NumberFormat("en").format(value)} ${label}${value === 1 ? "" : "s"}`;
}

export function sourceTypeDistribution(sources: KnowledgeSource[]) {
  return sources.reduce<Record<string, number>>((acc, source) => {
    acc[source.sourceType] = (acc[source.sourceType] ?? 0) + 1;
    return acc;
  }, {});
}

export function overviewStats(dataset: KnowledgeWorkspaceDataset) {
  return {
    sources: dataset.sources.length,
    revisions: dataset.sources.reduce((total, source) => total + source.revisions.length, 0),
    activeJobs: dataset.jobs.filter((job) => ["QUEUED", "RUNNING", "RETRY_SCHEDULED"].includes(job.status)).length,
    failedJobs: dataset.jobs.filter((job) => job.status === "FAILED").length,
    claims: dataset.claims.length,
    entities: dataset.entities.length,
    relations: dataset.relations.length,
    conflicts: dataset.conflicts.filter((conflict) => conflict.status === "UNRESOLVED").length,
    workflows: dataset.workflows.filter((workflow) => workflow.status === "RUNNING").length,
    artifacts: dataset.artifacts.length,
    approvals: dataset.approvals.filter((approval) => approval.status === "AWAITING_APPROVAL").length,
  };
}

export function demoOverviewSummary(dataset: KnowledgeWorkspaceDataset) {
  const versionUpdates = dataset.sources.filter((source) => source.revisions.length > 1).length;
  const formalArtifacts = dataset.artifacts.filter((artifact) => artifact.artifactType === "Decision Memo").length;
  const pendingActions = dataset.approvals.filter((approval) => approval.status === "AWAITING_APPROVAL").length;
  return [
    { label: "资料来源", value: dataset.sources.length, detail: "全部属于 Project Atlas" },
    { label: "主要版本更新", value: versionUpdates, detail: "SQLite → PostgreSQL 16 + pgvector" },
    { label: "知识冲突", value: dataset.conflicts.length, detail: "旧知识更新与行动审批冲突" },
    { label: "正式产物", value: formalArtifacts, detail: "包含当前与过期 Decision Memo" },
    { label: "待审批行动", value: pendingActions, detail: "外部通知草稿等待审批" },
  ];
}

export function filterSources(
  sources: KnowledgeSource[],
  query: string,
  type: string,
  status: string,
): KnowledgeSource[] {
  const normalized = query.trim().toLowerCase();
  return sources.filter((source) => {
    const matchesQuery =
      normalized.length === 0 ||
      source.title.toLowerCase().includes(normalized) ||
      source.canonicalUri.toLowerCase().includes(normalized);
    const matchesType = type === "all" || source.sourceType === type;
    const matchesStatus = status === "all" || source.status === status;
    return matchesQuery && matchesType && matchesStatus;
  });
}

export function searchKnowledge(dataset: KnowledgeWorkspaceDataset, query: string) {
  const normalized = query.trim().toLowerCase();
  if (!normalized) return dataset.searchResults;
  return dataset.searchResults.filter(
    (result) =>
      result.title.toLowerCase().includes(normalized) ||
      result.snippet.toLowerCase().includes(normalized) ||
      result.citationIds.some((id) => {
        const citation = dataset.citations.find((item) => item.citationId === id);
        return citation?.quotedText.toLowerCase().includes(normalized);
      }),
  );
}

export function claimsForConflict(
  dataset: KnowledgeWorkspaceDataset,
  conflict: KnowledgeConflict,
): KnowledgeClaim[] {
  return conflict.claimIds
    .map((claimId) => dataset.claims.find((claim) => claim.id === claimId))
    .filter((claim): claim is KnowledgeClaim => Boolean(claim));
}

export function artifactForActivity(
  dataset: KnowledgeWorkspaceDataset,
  event: KnowledgeActivityEvent,
): KnowledgeArtifact | undefined {
  return dataset.artifacts.find((artifact) => event.detail.includes(artifact.title));
}

export function buildDemoImportPayload(draft: KnowledgeImportDraft) {
  return {
    source_type: draft.mode,
    source_uri: draft.sourceUri,
    media_type: draft.mediaType ?? null,
    metadata: {
      title: draft.title ?? draft.sourceUri.split("/").pop() ?? "Untitled source",
    },
    idempotency_key: `demo-${draft.mode}-${draft.sourceUri}`,
  };
}

export function createDemoImportResult(draft: KnowledgeImportDraft): DemoImportResult {
  const accepted: KnowledgeJobAccepted = {
    job_id: draft.mode === "url" ? "demo-url-import-job" : "demo-file-import-job",
    status: "QUEUED",
    status_url: "/api/knowledge/jobs/demo-import",
    events_url: "/api/knowledge/jobs/demo-import/events",
  };
  return { ...accepted, acceptedAt: new Date("2026-06-17T08:00:00.000Z").toISOString() };
}

export function hasTrustedIdentityField(value: unknown): boolean {
  if (!value || typeof value !== "object") return false;
  const trusted = new Set(["workspace_id", "user_id", "thread_id", "actor_id", "_trusted_user_id", "_trusted_actor_id"]);
  return Object.keys(value as Record<string, unknown>).some((key) => trusted.has(key));
}
