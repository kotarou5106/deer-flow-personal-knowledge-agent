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
  { href: "/workspace/knowledge", label: "Overview" },
  { href: "/workspace/knowledge/sources", label: "Sources" },
  { href: "/workspace/knowledge/search", label: "Search" },
  { href: "/workspace/knowledge/analysis", label: "Analysis" },
  { href: "/workspace/knowledge/graph", label: "Graph" },
  { href: "/workspace/knowledge/conflicts", label: "Conflicts" },
  { href: "/workspace/knowledge/workflows", label: "Workflows" },
  { href: "/workspace/knowledge/artifacts", label: "Artifacts" },
  { href: "/workspace/knowledge/approvals", label: "Approvals" },
  { href: "/workspace/knowledge/activity", label: "Activity" },
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
      result.snippet.toLowerCase().includes(normalized),
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
