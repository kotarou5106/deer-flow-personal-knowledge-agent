"use client";

import { useQuery } from "@tanstack/react-query";
import {
  ActivityIcon,
  AlertTriangleIcon,
  BarChart3Icon,
  BookOpenIcon,
  CheckCircle2Icon,
  CircleAlertIcon,
  FileTextIcon,
  FilterIcon,
  GitBranchIcon,
  GitCompareIcon,
  Layers3Icon,
  Loader2Icon,
  NetworkIcon,
  PauseIcon,
  PlayIcon,
  RefreshCwIcon,
  SearchIcon,
  ShieldCheckIcon,
  UploadIcon,
  XCircleIcon,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import {
  WorkspaceBody,
  WorkspaceContainer,
  WorkspaceHeader,
} from "@/components/workspace/workspace-container";
import { useKnowledgeClient, useKnowledgeConfig } from "@/core/knowledge";
import {
  buildDemoImportPayload,
  claimsForConflict,
  createDemoImportResult,
  filterSources,
  formatKnowledgeCount,
  formatKnowledgeDate,
  getDemoKnowledgeWorkspace,
  knowledgeRoutes,
  overviewStats,
  searchKnowledge,
  sourceTypeDistribution,
  workflowTypeLabels,
} from "@/core/knowledge/workspace-model";
import type {
  KnowledgeActivityEvent,
  KnowledgeArtifact,
  KnowledgeCitation,
  KnowledgeChunk,
  KnowledgeClaim,
  KnowledgeConflict,
  KnowledgeImportDraft,
  KnowledgeRevision,
  KnowledgeSource,
  KnowledgeSourceStatus,
  KnowledgeSourceType,
  KnowledgeWorkflow,
  KnowledgeWorkspaceDataset,
  KnowledgeApproval,
  RiskLevel,
  SearchResult,
  WorkflowStatus,
  WorkflowType,
  ApprovalStatus,
} from "@/core/knowledge/workspace-types";
import { cn } from "@/lib/utils";

export type KnowledgeWorkspaceView =
  | "overview"
  | "sources"
  | "source-detail"
  | "search"
  | "analysis"
  | "graph"
  | "conflicts"
  | "workflows"
  | "artifacts"
  | "approvals"
  | "activity";

type KnowledgeWorkspacePageProps = {
  view: KnowledgeWorkspaceView;
  sourceId?: string;
};

export function KnowledgeWorkspacePage({ view, sourceId }: KnowledgeWorkspacePageProps) {
  const config = useKnowledgeConfig();
  const dataset = useMemo(() => getDemoKnowledgeWorkspace(), []);
  const [citation, setCitation] = useState<KnowledgeCitation | null>(null);

  useEffect(() => {
    document.title = `${titleForView(view)} - Knowledge - DeerFlow`;
  }, [view]);

  return (
    <WorkspaceContainer>
      <WorkspaceHeader />
      <WorkspaceBody className="items-stretch overflow-hidden">
        <div className="flex h-full w-full flex-col lg:flex-row">
          <aside className="border-b bg-background/80 lg:w-60 lg:border-r lg:border-b-0">
            <KnowledgeNav current={view} demoMode={config.demoMode} />
          </aside>
          <main className="min-w-0 flex-1 overflow-hidden">
            <ScrollArea className="h-full">
              <div className="mx-auto flex w-full max-w-7xl flex-col gap-4 p-4 md:p-6">
                <KnowledgePageHeader view={view} demoMode={config.demoMode} />
                {!config.demoMode ? <ProductionNotice /> : null}
                {renderView({
                  view,
                  sourceId,
                  dataset,
                  demoMode: config.demoMode,
                  onOpenCitation: setCitation,
                })}
              </div>
            </ScrollArea>
          </main>
        </div>
      </WorkspaceBody>
      <CitationSheet citation={citation} onOpenChange={(open) => !open && setCitation(null)} />
    </WorkspaceContainer>
  );
}

function renderView({
  view,
  sourceId,
  dataset,
  demoMode,
  onOpenCitation,
}: {
  view: KnowledgeWorkspaceView;
  sourceId?: string;
  dataset: KnowledgeWorkspaceDataset;
  demoMode: boolean;
  onOpenCitation: (citation: KnowledgeCitation) => void;
}) {
  if (!demoMode) {
    return <ProductionGatewayView view={view} sourceId={sourceId} onOpenCitation={onOpenCitation} />;
  }
  if (view === "overview") return <OverviewView dataset={dataset} onOpenCitation={onOpenCitation} />;
  if (view === "sources") return <SourcesView dataset={dataset} onOpenCitation={onOpenCitation} />;
  if (view === "source-detail") return <SourceDetailView dataset={dataset} sourceId={sourceId} onOpenCitation={onOpenCitation} />;
  if (view === "search") return <SearchView dataset={dataset} onOpenCitation={onOpenCitation} />;
  if (view === "analysis") return <AnalysisView dataset={dataset} onOpenCitation={onOpenCitation} />;
  if (view === "graph") return <GraphView dataset={dataset} onOpenCitation={onOpenCitation} />;
  if (view === "conflicts") return <ConflictsView dataset={dataset} onOpenCitation={onOpenCitation} />;
  if (view === "workflows") return <WorkflowsView dataset={dataset} demoMode={demoMode} />;
  if (view === "artifacts") return <ArtifactsView dataset={dataset} onOpenCitation={onOpenCitation} />;
  if (view === "approvals") return <ApprovalsView dataset={dataset} demoMode={demoMode} />;
  return <ActivityView dataset={dataset} />;
}

function titleForView(view: KnowledgeWorkspaceView) {
  if (view === "source-detail") return "Source Detail";
  return view[0]!.toUpperCase() + view.slice(1).replace("-", " ");
}

function KnowledgeNav({ current, demoMode }: { current: KnowledgeWorkspaceView; demoMode: boolean }) {
  return (
    <nav aria-label="Knowledge workspace" className="flex gap-1 overflow-x-auto p-2 lg:flex-col">
      {knowledgeRoutes.map((route) => {
        const key = route.href.split("/").at(-1) ?? "overview";
        const active = current === (key === "knowledge" ? "overview" : key);
        return (
          <Link
            key={route.href}
            href={route.href}
            className={cn(
              "flex shrink-0 items-center gap-2 rounded-md px-3 py-2 text-sm text-muted-foreground outline-none transition hover:bg-accent hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring",
              active && "bg-accent text-foreground",
            )}
          >
            <NavIcon label={route.label} />
            <span>{route.label}</span>
          </Link>
        );
      })}
      <Badge variant={demoMode ? "secondary" : "outline"} className="mx-2 mt-1 justify-center rounded-md">
        {demoMode ? "Demo mode" : "Production"}
      </Badge>
    </nav>
  );
}

function NavIcon({ label }: { label: string }) {
  const className = "size-4";
  if (label === "Overview") return <BarChart3Icon className={className} aria-hidden="true" />;
  if (label === "Sources") return <BookOpenIcon className={className} aria-hidden="true" />;
  if (label === "Search") return <SearchIcon className={className} aria-hidden="true" />;
  if (label === "Analysis") return <FileTextIcon className={className} aria-hidden="true" />;
  if (label === "Graph") return <NetworkIcon className={className} aria-hidden="true" />;
  if (label === "Conflicts") return <GitCompareIcon className={className} aria-hidden="true" />;
  if (label === "Workflows") return <GitBranchIcon className={className} aria-hidden="true" />;
  if (label === "Artifacts") return <Layers3Icon className={className} aria-hidden="true" />;
  if (label === "Approvals") return <ShieldCheckIcon className={className} aria-hidden="true" />;
  return <ActivityIcon className={className} aria-hidden="true" />;
}

function KnowledgePageHeader({ view, demoMode }: { view: KnowledgeWorkspaceView; demoMode: boolean }) {
  return (
    <div className="flex flex-col gap-3 border-b pb-4 md:flex-row md:items-center md:justify-between">
      <div>
        <div className="flex items-center gap-2">
          <h1 className="text-2xl font-semibold tracking-normal">{titleForView(view)}</h1>
          <Badge variant="outline" className="rounded-md">
            {demoMode ? "Deterministic demo" : "Gateway-backed"}
          </Badge>
        </div>
        <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
          Trace sources into evidence, claims, conflicts, workflows, artifacts, approvals, and action audit.
        </p>
      </div>
      <ServiceStatus demoMode={demoMode} />
    </div>
  );
}

function ServiceStatus({ demoMode }: { demoMode: boolean }) {
  return (
    <div className="flex items-center gap-2 rounded-md border px-3 py-2 text-sm">
      {demoMode ? <CheckCircle2Icon className="size-4 text-emerald-600" /> : <CircleAlertIcon className="size-4 text-amber-600" />}
      <span>{demoMode ? "Demo data loaded" : "Some API surfaces unavailable"}</span>
    </div>
  );
}

function ProductionNotice() {
  return (
    <Alert>
      <CircleAlertIcon className="size-4" />
      <AlertTitle>Production mode is intentionally conservative</AlertTitle>
      <AlertDescription>
        This UI will not invent Knowledge data. Existing Gateway endpoints can be wired in the next integration stage; unavailable panels list the missing contracts.
      </AlertDescription>
    </Alert>
  );
}

function ProductionUnavailable({ view }: { view: KnowledgeWorkspaceView }) {
  return (
    <Empty className="min-h-[360px] border">
      <EmptyHeader>
        <EmptyMedia variant="icon">
          <CircleAlertIcon />
        </EmptyMedia>
        <EmptyTitle>{titleForView(view)} needs integration data</EmptyTitle>
        <EmptyDescription>
          Demo mode shows the complete workspace. Production mode only uses formal Gateway contracts and will not call missing endpoints.
        </EmptyDescription>
      </EmptyHeader>
      <Link href="/workspace/knowledge/activity">
        <Button variant="outline">View available activity surface</Button>
      </Link>
    </Empty>
  );
}

function ProductionGatewayView({
  view,
  sourceId,
  onOpenCitation,
}: {
  view: KnowledgeWorkspaceView;
  sourceId?: string;
  onOpenCitation: (citation: KnowledgeCitation) => void;
}) {
  const client = useKnowledgeClient();
  const [datasetState, setDatasetState] = useState<{
    loading: boolean;
    error: Error | null;
    dataset: KnowledgeWorkspaceDataset;
  }>(() => ({ loading: true, error: null, dataset: emptyProductionDataset() }));

  useEffect(() => {
    if (view === "search" || view === "analysis" || view === "graph") return;
    const controller = new AbortController();
    let cancelled = false;
    setDatasetState((current) => ({ ...current, loading: true, error: null }));

    async function loadDataset() {
      try {
        const [overview, sourcesEnvelope, activityEnvelope] = await Promise.all([
          client.getOverview({ signal: controller.signal }),
          client.listSources({ limit: 100, offset: 0 }, { signal: controller.signal }),
          client.listActivity({ limit: 100, offset: 0 }, { signal: controller.signal }),
        ]);
        const [claims, conflicts, workflowsEnvelope, artifactsEnvelope, approvalsEnvelope, sourceDetail] = await Promise.all([
          client.listClaims({ limit: 100, offset: 0 }, { signal: controller.signal }).catch(() => undefined),
          client.listConflicts({ limit: 100, offset: 0 }, { signal: controller.signal }).catch(() => undefined),
          client.listWorkflows({ limit: 100, offset: 0 }, { signal: controller.signal }).catch(() => undefined),
          client.listArtifacts({ limit: 100, offset: 0 }, { signal: controller.signal }).catch(() => undefined),
          client.listApprovals({ limit: 100, offset: 0 }, { signal: controller.signal }).catch(() => undefined),
          view === "source-detail" && sourceId
            ? client.getSourceDetail(sourceId, { signal: controller.signal }).catch(() => undefined)
            : Promise.resolve(undefined),
        ]);
        if (!cancelled) {
          setDatasetState({
            loading: false,
            error: null,
            dataset: buildProductionDataset({
              overview,
              sourcesEnvelope,
              sourceDetail,
              activityEnvelope,
              claims,
              conflicts,
              workflowsEnvelope,
              artifactsEnvelope,
              approvalsEnvelope,
            }),
          });
        }
      } catch (error) {
        if (!cancelled) {
          setDatasetState({
            loading: false,
            error: error instanceof Error ? error : new Error("Production Knowledge data could not be loaded."),
            dataset: emptyProductionDataset(),
          });
        }
      }
    }

    void loadDataset();
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [client, sourceId, view]);

  if (view === "search") {
    return <ProductionSearchView onOpenCitation={onOpenCitation} />;
  }
  if (view === "analysis" || view === "graph") {
    return <ProductionUnavailable view={view} />;
  }

  if (datasetState.loading) return <Skeleton className="h-72" />;

  if (datasetState.error) {
    return (
      <Alert variant="destructive">
        <AlertTriangleIcon className="size-4" />
        <AlertTitle>Knowledge Gateway unavailable</AlertTitle>
        <AlertDescription>{datasetState.error.message}</AlertDescription>
      </Alert>
    );
  }

  const dataset = datasetState.dataset;

  if (view === "overview") return <OverviewView dataset={dataset} onOpenCitation={onOpenCitation} />;
  if (view === "sources") return <SourcesView dataset={dataset} onOpenCitation={onOpenCitation} />;
  if (view === "source-detail") return <SourceDetailView dataset={dataset} sourceId={sourceId} onOpenCitation={onOpenCitation} />;
  if (view === "conflicts") return <ConflictsView dataset={dataset} onOpenCitation={onOpenCitation} />;
  if (view === "workflows") return <WorkflowsView dataset={dataset} demoMode={false} />;
  if (view === "artifacts") return <ArtifactsView dataset={dataset} onOpenCitation={onOpenCitation} />;
  if (view === "approvals") return <ApprovalsView dataset={dataset} demoMode={false} />;
  return <ActivityView dataset={dataset} />;
}

function ProductionSearchView({ onOpenCitation }: { onOpenCitation: (citation: KnowledgeCitation) => void }) {
  const client = useKnowledgeClient();
  const [query, setQuery] = useState("");
  const [submittedQuery, setSubmittedQuery] = useState<string | null>(null);
  const canFetchKnowledge = typeof window !== "undefined";
  const searchQuery = useQuery({
    queryKey: ["knowledge", "workspace", "search", submittedQuery],
    queryFn: ({ signal }) => client.search({ query: submittedQuery ?? "", context_budget: 4000 }, { signal }),
    enabled: canFetchKnowledge && Boolean(submittedQuery),
    retry: false,
  });
  const dataset = emptyProductionDataset();
  const { results, citations } = mapSearchPayload(searchQuery.data);
  dataset.citations = citations;
  dataset.searchResults = results;

  return (
    <div className="grid gap-4">
      <Card>
        <CardHeader><CardTitle>Hybrid retrieval</CardTitle><CardDescription>Production search calls the Gateway retrieval endpoint.</CardDescription></CardHeader>
        <CardContent className="space-y-3">
          <div className="grid gap-2 md:grid-cols-[1fr_auto]">
            <Input aria-label="Knowledge search query" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search your knowledge base" />
            <Button onClick={() => setSubmittedQuery(query.trim())} disabled={searchQuery.isLoading || query.trim().length === 0}>{searchQuery.isLoading ? <Loader2Icon className="size-4 animate-spin" /> : <SearchIcon className="size-4" />} Search</Button>
          </div>
        </CardContent>
      </Card>
      {searchQuery.error ? (
        <Alert variant="destructive"><AlertTriangleIcon className="size-4" /><AlertTitle>Search failed</AlertTitle><AlertDescription>{searchQuery.error instanceof Error ? searchQuery.error.message : "Search request failed."}</AlertDescription></Alert>
      ) : searchQuery.isLoading ? <Skeleton className="h-48" /> : !submittedQuery ? <EmptyState title="Enter a query to search production knowledge" /> : (
        <div className="grid gap-3">
          <div className="text-sm text-muted-foreground">{formatKnowledgeCount(results.length, "result")}</div>
          {results.length === 0 ? <EmptyState title="No evidence matched the query" /> : results.map((result) => (
            <Card key={result.id}>
              <CardHeader><CardTitle>{result.title}</CardTitle><CardDescription>{result.retrievalChannels.join(" / ") || "Gateway retrieval"}</CardDescription></CardHeader>
              <CardContent className="space-y-3">
                <p>{result.snippet}</p>
                <CitationRow citationIds={result.citationIds} dataset={dataset} onOpenCitation={onOpenCitation} />
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

function emptyProductionDataset(): KnowledgeWorkspaceDataset {
  return {
    sources: [],
    citations: [],
    entities: [],
    claims: [],
    relations: [],
    jobs: [],
    jobEvents: {},
    searchResults: [],
    analysis: {
      query: "",
      answer: "",
      supportedFacts: [],
      inferredConclusions: [],
      unsupportedClaims: [],
      unresolvedQuestions: [],
      sourceIds: [],
    },
    graph: { nodes: [], edges: [] },
    conflicts: [],
    workflows: [],
    artifacts: [],
    approvals: [],
    activity: [],
  };
}

function buildProductionDataset(input: {
  overview?: Record<string, unknown>;
  sourcesEnvelope?: { data: Record<string, unknown>[] };
  sourceDetail?: Record<string, unknown>;
  activityEnvelope?: { data: Record<string, unknown>[] };
  claims?: Record<string, unknown>;
  conflicts?: Record<string, unknown>;
  workflowsEnvelope?: { data: Record<string, unknown>[] };
  artifactsEnvelope?: { data: Record<string, unknown>[] };
  approvalsEnvelope?: { data: Record<string, unknown>[] };
}): KnowledgeWorkspaceDataset {
  const dataset = emptyProductionDataset();
  const sources = input.sourcesEnvelope?.data ?? [];
  dataset.sources = sources.map(mapSourceSummary);

  const sourceDetail = input.sourceDetail;
  if (sourceDetail) {
    const detailSource = mapSourceDetail(sourceDetail);
    dataset.sources = [
      detailSource,
      ...dataset.sources.filter((source) => source.id !== detailSource.id),
    ];
    dataset.citations = mapEvidenceToCitations(sourceDetail, detailSource);
    dataset.jobs = mapDetailJobs(sourceDetail);
  }

  dataset.claims = readArray(input.claims, "data").map(mapClaim);
  dataset.conflicts = readArray(input.conflicts, "data").map(mapConflict);
  dataset.workflows = (input.workflowsEnvelope?.data ?? []).map(mapWorkflow);
  dataset.artifacts = (input.artifactsEnvelope?.data ?? []).map(mapArtifact);
  dataset.approvals = (input.approvalsEnvelope?.data ?? []).map(mapApproval);
  dataset.activity = [
    ...mapActivity(input.activityEnvelope?.data ?? []),
    ...mapOverviewActivity(input.overview),
  ];
  return dataset;
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function readArray(value: unknown, key: string): Record<string, unknown>[] {
  const array = asRecord(value)[key];
  return Array.isArray(array) ? array.map(asRecord) : [];
}

function readString(value: Record<string, unknown>, ...keys: string[]): string {
  for (const key of keys) {
    const item = value[key];
    if (typeof item === "string" && item.length > 0) return item;
  }
  return "";
}

function readNumber(value: Record<string, unknown>, key: string, fallback = 0): number {
  const item = value[key];
  return typeof item === "number" && Number.isFinite(item) ? item : fallback;
}

function mapSourceType(value: string): KnowledgeSourceType {
  const lower = value.toLowerCase();
  if (["pdf", "docx", "pptx", "xlsx", "markdown", "txt", "html", "url"].includes(lower)) return lower as KnowledgeSourceType;
  if (lower.includes("url") || lower.includes("html")) return "url";
  if (lower.includes("markdown") || lower === "md") return "markdown";
  if (lower.includes("text") || lower.includes("file")) return "txt";
  return "txt";
}

function mapSourceStatus(value: string): KnowledgeSourceStatus {
  const upper = value.toUpperCase();
  if (["ACTIVE", "PARSING", "INDEXING", "FAILED", "ARCHIVED"].includes(upper)) return upper as KnowledgeSourceStatus;
  return "ACTIVE";
}

function mapSourceSummary(raw: Record<string, unknown>): KnowledgeSource {
  const id = readString(raw, "source_id", "id");
  const title = readString(raw, "title") || readString(raw, "canonical_uri", "canonicalUri") || id;
  return {
    id,
    sourceType: mapSourceType(readString(raw, "source_type", "sourceType")),
    canonicalUri: readString(raw, "canonical_uri", "canonicalUri"),
    title,
    status: mapSourceStatus(readString(raw, "status")),
    currentRevisionId: readString(raw, "current_revision_id", "revision_id", "latest_revision_id"),
    claimCount: readNumber(raw, "claim_count"),
    chunkCount: readNumber(raw, "chunk_count"),
    updatedAt: readString(raw, "updated_at", "created_at"),
    revisions: [],
    diff: [],
  };
}

function mapRevision(raw: Record<string, unknown>, chunks: KnowledgeChunk[]): KnowledgeRevision {
  const id = readString(raw, "revision_id", "id");
  return {
    id,
    sourceId: readString(raw, "source_id", "sourceId"),
    revisionNumber: readNumber(raw, "revision_number", 1),
    previousRevisionId: readString(raw, "previous_revision_id") || undefined,
    contentHash: readString(raw, "content_hash"),
    parseStatus: readString(raw, "parse_status").toUpperCase() === "FAILED" ? "FAILED" : readString(raw, "parse_status").toUpperCase() === "PENDING" ? "PENDING" : "SUCCEEDED",
    indexStatus: readString(raw, "index_status").toUpperCase() === "FAILED" ? "FAILED" : readString(raw, "index_status").toUpperCase() === "PENDING" ? "PENDING" : "SUCCEEDED",
    createdAt: readString(raw, "created_at"),
    chunks,
  };
}

function mapChunk(raw: Record<string, unknown>): KnowledgeChunk {
  return {
    id: readString(raw, "chunk_id", "id"),
    revisionId: readString(raw, "revision_id", "revisionId"),
    parentChunkId: readString(raw, "parent_chunk_id") || undefined,
    chunkIndex: readNumber(raw, "chunk_index"),
    tokenCount: readNumber(raw, "token_count"),
    content: readString(raw, "content"),
    pageNumber: readNumber(raw, "page_number") || undefined,
    sectionPath: Array.isArray(raw.section_path) ? raw.section_path.filter((item): item is string => typeof item === "string") : [],
    startOffset: readNumber(raw, "start_offset"),
    endOffset: readNumber(raw, "end_offset"),
  };
}

function mapSourceDetail(raw: Record<string, unknown>): KnowledgeSource {
  const source = mapSourceSummary(asRecord(raw.source));
  const chunks = readArray(raw, "chunks").map(mapChunk);
  const revisions = readArray(raw, "revisions").map((revision) => mapRevision(revision, chunks.filter((chunk) => chunk.revisionId === readString(revision, "revision_id", "id"))));
  const currentRevision = revisions.at(0);
  return {
    ...source,
    currentRevisionId: currentRevision?.id ?? source.currentRevisionId,
    claimCount: readArray(raw, "claims").length,
    chunkCount: chunks.length,
    updatedAt: source.updatedAt ?? currentRevision?.createdAt ?? "",
    revisions,
  };
}

function mapEvidenceToCitations(raw: Record<string, unknown>, source: KnowledgeSource): KnowledgeCitation[] {
  const revisions = source.revisions;
  const chunks = revisions.flatMap((revision) => revision.chunks);
  return readArray(raw, "evidence").map((span) => {
    const chunk = chunks.find((item) => item.id === readString(span, "chunk_id"));
    const revision = revisions.find((item) => item.id === chunk?.revisionId);
    return {
      citationId: readString(span, "evidence_span_id", "id"),
      sourceId: source.id,
      revisionId: revision?.id ?? "",
      chunkId: chunk?.id ?? "",
      evidenceSpanId: readString(span, "evidence_span_id", "id"),
      sourceTitle: source.title,
      sourceUri: source.canonicalUri,
      quotedText: readString(span, "quoted_text"),
      pageNumber: readNumber(span, "page_number") || undefined,
      sectionPath: chunk?.sectionPath,
      startOffset: readNumber(span, "start_offset"),
      endOffset: readNumber(span, "end_offset"),
      role: "direct",
    };
  });
}

function mapDetailJobs(raw: Record<string, unknown>): KnowledgeWorkspaceDataset["jobs"] {
  return readArray(raw, "jobs").map((job) => ({
    job_id: readString(job, "job_id", "id"),
    workspace_id: "",
    job_type: "ingestion",
    status: ["QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "CANCEL_REQUESTED", "CANCELLED", "RETRY_SCHEDULED"].includes(readString(job, "status")) ? readString(job, "status") as KnowledgeWorkspaceDataset["jobs"][number]["status"] : "SUCCEEDED",
    payload_hash: "",
    idempotency_key: null,
    attempt: 1,
    max_attempts: 1,
    progress: {},
    created_at: readString(job, "created_at"),
    started_at: null,
    completed_at: readString(job, "completed_at") || null,
    error_type: null,
    error_message: readString(job, "error") || null,
    result_reference: null,
  }));
}

function mapClaim(raw: Record<string, unknown>): KnowledgeClaim {
  return {
    id: readString(raw, "claim_id", "id"),
    text: readString(raw, "claim_text", "text"),
    normalizedSubject: readString(raw, "normalized_subject"),
    predicate: readString(raw, "predicate"),
    normalizedObject: readString(raw, "normalized_object"),
    stance: readString(raw, "stance").toUpperCase() === "CONTRADICTS" ? "CONTRADICTS" : readString(raw, "stance").toUpperCase() === "SUPPORTS" ? "SUPPORTS" : "NEUTRAL",
    confidence: readNumber(raw, "confidence"),
    status: "CURRENT_ACTIVE",
    citationIds: [],
  };
}

function mapConflict(raw: Record<string, unknown>): KnowledgeConflict {
  return {
    id: readString(raw, "conflict_group_id", "id"),
    classification: "POSSIBLE_CONFLICT",
    status: readString(raw, "status").toUpperCase() === "REVIEWED" ? "REVIEWED" : "UNRESOLVED",
    summary: readString(raw, "summary") || "Conflict requires review",
    claimIds: [],
    citationIds: [],
    scopeOrCondition: "",
    activeClaimId: "",
    affectedArtifactIds: [],
    recommendedNextStep: "Review the affected claims in the Knowledge domain.",
    updatedAt: readString(raw, "updated_at", "created_at"),
  };
}

function mapWorkflow(raw: Record<string, unknown>): KnowledgeWorkflow {
  const id = readString(raw, "workflow_run_id", "id");
  return {
    id,
    workflowType: (readString(raw, "workflow_type") as WorkflowType) || "decision_memo",
    title: readString(raw, "title") || readString(raw, "workflow_type") || id,
    status: (readString(raw, "status").toUpperCase() as WorkflowStatus) || "PENDING",
    currentStep: readString(raw, "current_step") || undefined,
    sourceIds: [],
    artifactIds: [],
    updatedAt: readString(raw, "updated_at", "created_at"),
    steps: readArray(raw, "steps").map((step) => ({
      key: readString(step, "step_key", "key"),
      label: readString(step, "step_key", "key"),
      status: (readString(step, "status").toUpperCase() as WorkflowStatus) || "PENDING",
      inputSummary: "",
      outputSummary: readString(asRecord(step.output_payload), "summary"),
      error: readString(step, "error_message") || undefined,
    })),
  };
}

function mapArtifact(raw: Record<string, unknown>): KnowledgeArtifact {
  return {
    id: readString(raw, "artifact_id", "id"),
    artifactType: readString(raw, "artifact_type"),
    title: readString(raw, "title") || readString(raw, "artifact_id", "id"),
    validationStatus: readString(raw, "validation_status", "status").toUpperCase() === "INVALID" ? "INVALID" : readString(raw, "validation_status", "status").toUpperCase() === "VALID" ? "VALID" : "PENDING",
    stalenessStatus: readString(raw, "staleness_status").toUpperCase() === "STALE" ? "STALE" : readString(raw, "staleness_status").toUpperCase() === "CURRENT" ? "CURRENT" : "UNKNOWN",
    createdAt: readString(raw, "created_at"),
    sourceIds: [],
    citationIds: [],
    staleReasons: [],
    markdown: readString(raw, "markdown"),
  };
}

function mapApproval(raw: Record<string, unknown>): KnowledgeApproval {
  const preview = asRecord(raw.action_preview);
  return {
    id: readString(raw, "approval_request_id", "id"),
    workflowId: readString(raw, "workflow_run_id"),
    actionType: readString(raw, "action_type"),
    payloadSummary: readString(preview, "summary", "target") || "Action preview available",
    payloadHash: readString(raw, "payload_hash"),
    requestedBy: "Gateway",
    riskLevel: (readString(raw, "risk_level").toUpperCase() as RiskLevel) || "LOW",
    status: (readString(raw, "status").toUpperCase() as ApprovalStatus) || "DRAFT",
    executionStatus: "PENDING",
    createdAt: readString(raw, "created_at", "requested_at"),
    decidedAt: readString(raw, "decided_at") || undefined,
    audit: ["Loaded from Gateway approval contract."],
  };
}

function mapActivity(rows: Record<string, unknown>[]): KnowledgeActivityEvent[] {
  return rows.map((row) => {
    const id = readString(row, "job_id", "id");
    return {
      id,
      type: "ingestion",
      status: readString(row, "status"),
      title: readString(row, "job_type") || "Knowledge job",
      createdAt: readString(row, "created_at"),
      detail: readString(row, "error_message") || readString(row, "error_type") || "Gateway job event",
    };
  });
}

function mapOverviewActivity(overview?: Record<string, unknown>): KnowledgeActivityEvent[] {
  return readArray(overview, "recent_sources").map((source) => ({
    id: readString(source, "source_id", "id"),
    type: "ingestion",
    status: readString(source, "status"),
    title: readString(source, "title") || "Knowledge source",
    linkedHref: `/workspace/knowledge/sources/${readString(source, "source_id", "id")}`,
    createdAt: readString(source, "updated_at", "created_at"),
    detail: readString(source, "canonical_uri"),
  }));
}

function mapSearchPayload(raw: unknown): { results: SearchResult[]; citations: KnowledgeCitation[] } {
  const record = asRecord(raw);
  const rows = readArray(record, "results").length > 0
    ? readArray(record, "results")
    : [...readArray(record, "retrieved_chunks"), ...readArray(record, "evidence_spans"), ...readArray(record, "claims")];
  const citations: KnowledgeCitation[] = [];
  const results = rows.map((row, index) => {
    const provenance = asRecord(row.provenance);
    const channel = readString(row, "retrieval_channel");
    const citationId = readString(provenance, "evidence_span_id") || readString(provenance, "chunk_id") || `search-citation-${index}`;
    const sourceId = readString(row, "source_id") || readString(provenance, "source_id");
    const revisionId = readString(row, "revision_id") || readString(provenance, "revision_id");
    const chunkId = readString(row, "chunk_id") || readString(provenance, "chunk_id");
    const content = readString(row, "content", "snippet");
    citations.push({
      citationId,
      sourceId,
      revisionId,
      chunkId,
      evidenceSpanId: readString(provenance, "evidence_span_id") || citationId,
      sourceTitle: readString(asRecord(row.metadata), "source_title") || sourceId || "Knowledge source",
      sourceUri: sourceId,
      quotedText: content,
      pageNumber: readNumber(provenance, "page_number") || undefined,
      sectionPath: Array.isArray(provenance.section_path) ? provenance.section_path.filter((item): item is string => typeof item === "string") : [],
      startOffset: readNumber(provenance, "start_offset"),
      endOffset: readNumber(provenance, "end_offset", content.length),
      role: row.is_context_expansion === true || row.direct_evidence === false ? "parent_context" : "direct",
    });
    return {
      id: readString(row, "candidate_id", "id") || `result-${index}`,
      title: readString(asRecord(row.metadata), "title") || readString(row, "candidate_type") || "Evidence result",
      snippet: content,
      sourceId,
      revisionId,
      citationIds: [citationId],
      retrievalChannels: mapRetrievalChannels(channel),
      relatedClaimIds: [],
      relatedEntityIds: [],
    };
  });
  return { results, citations };
}

function mapRetrievalChannels(channel: string): SearchResult["retrievalChannels"] {
  if (channel.includes("graph")) return ["Graph"];
  if (channel.includes("vector")) return ["Vector"];
  if (channel.includes("lexical")) return ["Lexical"];
  return ["Fused Result"];
}

function OverviewView({ dataset, onOpenCitation }: { dataset: KnowledgeWorkspaceDataset; onOpenCitation: (citation: KnowledgeCitation) => void }) {
  const stats = overviewStats(dataset);
  const distribution = sourceTypeDistribution(dataset.sources);
  return (
    <div className="grid gap-4">
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <Stat label="Sources" value={stats.sources} detail={Object.entries(distribution).map(([type, count]) => `${type}: ${count}`).join(" / ")} />
        <Stat label="Claims / Entities / Relations" value={`${stats.claims}/${stats.entities}/${stats.relations}`} detail={`${stats.revisions} current and historical revisions`} />
        <Stat label="Jobs" value={`${stats.activeJobs} active`} detail={`${stats.failedJobs} failed jobs need review`} />
        <Stat label="Approvals" value={stats.approvals} detail={`${stats.conflicts} unresolved conflicts`} />
      </div>
      <div className="grid gap-4 xl:grid-cols-[1.5fr_1fr]">
        <Card>
          <CardHeader>
            <CardTitle>Recent source and workflow activity</CardTitle>
            <CardDescription>Evidence-first timeline across ingestion, workflow, artifact, approval, and update events.</CardDescription>
          </CardHeader>
          <CardContent>
            <ActivityList events={dataset.activity.slice(0, 5)} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Decision readiness</CardTitle>
            <CardDescription>Latest artifact, pending approval, and unresolved conflict.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <ArtifactSummary artifact={dataset.artifacts[0]!} onOpenCitation={onOpenCitation} dataset={dataset} />
            <Separator />
            <ConflictSummary conflict={dataset.conflicts[0]!} dataset={dataset} onOpenCitation={onOpenCitation} />
          </CardContent>
        </Card>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Running work</CardTitle>
          <CardDescription>Job and workflow progress stays observable from the control center.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-2">
          {dataset.jobs.map((job) => <JobProgressCard key={job.job_id} job={job} events={dataset.jobEvents[job.job_id] ?? []} />)}
        </CardContent>
      </Card>
    </div>
  );
}

function Stat({ label, value, detail }: { label: string; value: string | number; detail: string }) {
  return (
    <Card className="gap-3 py-4">
      <CardHeader className="px-4">
        <CardDescription>{label}</CardDescription>
        <CardTitle className="text-2xl">{value}</CardTitle>
      </CardHeader>
      <CardContent className="px-4 text-sm text-muted-foreground">{detail}</CardContent>
    </Card>
  );
}

function SourcesView({ dataset, onOpenCitation }: { dataset: KnowledgeWorkspaceDataset; onOpenCitation: (citation: KnowledgeCitation) => void }) {
  const [query, setQuery] = useState("");
  const [type, setType] = useState("all");
  const [status, setStatus] = useState("all");
  const sources = filterSources(dataset.sources, query, type, status);
  return (
    <div className="grid gap-4">
      <ImportDialog />
      <Card>
        <CardHeader>
          <CardTitle>Source library</CardTitle>
          <CardDescription>Search, filter, and inspect current revision, chunks, claims, and ingestion status.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-2 md:grid-cols-[1fr_180px_180px]">
            <Input aria-label="Search sources" placeholder="Search source title or URI" value={query} onChange={(event) => setQuery(event.target.value)} />
            <Select value={type} onValueChange={setType}>
              <SelectTrigger aria-label="Filter source type"><SelectValue placeholder="Type" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All types</SelectItem>
                {["pdf", "markdown", "xlsx", "url"].map((item) => <SelectItem key={item} value={item}>{item.toUpperCase()}</SelectItem>)}
              </SelectContent>
            </Select>
            <Select value={status} onValueChange={setStatus}>
              <SelectTrigger aria-label="Filter source status"><SelectValue placeholder="Status" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All statuses</SelectItem>
                {["ACTIVE", "INDEXING", "FAILED"].map((item) => <SelectItem key={item} value={item}>{item}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          {sources.length === 0 ? <EmptyState title="No sources match these filters" /> : (
            <div className="overflow-x-auto rounded-md border">
              <table className="w-full min-w-[840px] text-sm">
                <thead className="bg-muted/50 text-left text-muted-foreground">
                  <tr>
                    <th className="px-3 py-2 font-medium">Source</th>
                    <th className="px-3 py-2 font-medium">Type</th>
                    <th className="px-3 py-2 font-medium">Revision</th>
                    <th className="px-3 py-2 font-medium">Status</th>
                    <th className="px-3 py-2 font-medium">Claims / Chunks</th>
                    <th className="px-3 py-2 font-medium">Updated</th>
                  </tr>
                </thead>
                <tbody>
                  {sources.map((source) => (
                    <tr key={source.id} className="border-t hover:bg-muted/30">
                      <td className="px-3 py-3">
                        <Link className="font-medium underline-offset-4 hover:underline" href={`/workspace/knowledge/sources/${source.id}`}>{source.title}</Link>
                        <div className="truncate text-xs text-muted-foreground">{source.canonicalUri}</div>
                      </td>
                      <td className="px-3 py-3"><Badge variant="outline">{source.sourceType.toUpperCase()}</Badge></td>
                      <td className="px-3 py-3">rev {source.revisions.find((revision) => revision.id === source.currentRevisionId)?.revisionNumber}</td>
                      <td className="px-3 py-3"><StatusBadge value={source.status} /></td>
                      <td className="px-3 py-3">{source.claimCount} / {source.chunkCount}</td>
                      <td className="px-3 py-3">{formatKnowledgeDate(source.updatedAt)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>Recent ingestion evidence</CardTitle></CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-2">
          {dataset.citations.slice(0, 2).map((citation) => (
            <CitationButton key={citation.citationId} citation={citation} onOpenCitation={onOpenCitation} />
          ))}
        </CardContent>
      </Card>
    </div>
  );
}

function ImportDialog() {
  const client = useKnowledgeClient();
  const config = useKnowledgeConfig();
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<"file" | "url">("file");
  const [sourceUri, setSourceUri] = useState("deerflow://uploads/new-brief.pdf");
  const [acceptedJob, setAcceptedJob] = useState<string | null>(null);
  const [isSubmitting, setSubmitting] = useState(false);

  async function submit() {
    const draft: KnowledgeImportDraft = {
      mode,
      sourceUri,
      mediaType: mode === "file" ? mediaTypeForFileUri(sourceUri) : null,
      title: sourceUri.split("/").pop(),
    };
    const payload = buildDemoImportPayload(draft);
    setSubmitting(true);
    try {
      const result = await client.createIngestion(payload);
      setAcceptedJob(result.job_id);
      toast.success("Knowledge ingestion accepted");
    } catch (error) {
      if (config.demoMode) {
        const result = createDemoImportResult(draft);
        setAcceptedJob(result.job_id);
        toast.success("Demo ingestion accepted");
        return;
      }
      toast.error(error instanceof Error ? error.message : "Knowledge ingestion failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button className="w-fit"><UploadIcon className="size-4" /> Import source</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Import Knowledge source</DialogTitle>
          <DialogDescription>TXT, Markdown, HTML, DOCX, PPTX, XLSX, PDF, and URL imports are represented by ingestion jobs.</DialogDescription>
        </DialogHeader>
        <Tabs value={mode} onValueChange={(value) => setMode(value as "file" | "url")}>
          <TabsList><TabsTrigger value="file">File upload</TabsTrigger><TabsTrigger value="url">URL import</TabsTrigger></TabsList>
          <TabsContent value="file" className="space-y-3">
            <div className="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground">Drag a file here or choose a deterministic demo file path.</div>
            <Input aria-label="File URI" value={sourceUri} onChange={(event) => setSourceUri(event.target.value)} />
          </TabsContent>
          <TabsContent value="url" className="space-y-3">
            <Input aria-label="URL" value={sourceUri} onChange={(event) => setSourceUri(event.target.value)} placeholder="https://example.com/research" />
            {sourceUri.startsWith("http") ? null : <p className="text-sm text-destructive">URL imports must start with http or https.</p>}
          </TabsContent>
        </Tabs>
        {acceptedJob ? <JobAcceptedNotice jobId={acceptedJob} /> : null}
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>Close</Button>
          <Button onClick={submit} disabled={isSubmitting || (mode === "url" && !sourceUri.startsWith("http"))}>
            {isSubmitting ? <Loader2Icon className="size-4 animate-spin" /> : <UploadIcon className="size-4" />}
            Submit import
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function mediaTypeForFileUri(sourceUri: string): string | null {
  const normalized = sourceUri.split("?")[0]?.toLowerCase() ?? "";
  if (normalized.endsWith(".txt")) return "text/plain";
  if (normalized.endsWith(".md") || normalized.endsWith(".markdown")) return "text/markdown";
  if (normalized.endsWith(".html") || normalized.endsWith(".htm")) return "text/html";
  if (normalized.endsWith(".pdf")) return "application/pdf";
  if (normalized.endsWith(".docx")) return "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
  if (normalized.endsWith(".pptx")) return "application/vnd.openxmlformats-officedocument.presentationml.presentation";
  if (normalized.endsWith(".xlsx")) return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
  return null;
}

function JobAcceptedNotice({ jobId }: { jobId: string }) {
  return (
    <Alert>
      <CheckCircle2Icon className="size-4" />
      <AlertTitle>202 Accepted</AlertTitle>
      <AlertDescription>Job {jobId} is now observable through status and events.</AlertDescription>
    </Alert>
  );
}

function SourceDetailView({ dataset, sourceId, onOpenCitation }: { dataset: KnowledgeWorkspaceDataset; sourceId?: string; onOpenCitation: (citation: KnowledgeCitation) => void }) {
  const source = dataset.sources.find((item) => item.id === sourceId) ?? dataset.sources[0];
  if (!source) return <EmptyState title="Source not found" />;
  const currentRevision = source.revisions.find((revision) => revision.id === source.currentRevisionId) ?? source.revisions[0];
  const citations = dataset.citations.filter((citation) => citation.sourceId === source.id);
  return (
    <div className="grid gap-4">
      <Card>
        <CardHeader>
          <CardTitle>{source.title}</CardTitle>
          <CardDescription>{source.canonicalUri}</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-4">
          <Meta label="Type" value={source.sourceType.toUpperCase()} />
          <Meta label="Status" value={source.status} />
          <Meta label="Current revision" value={`rev ${currentRevision?.revisionNumber ?? "unknown"}`} />
          <Meta label="Updated" value={formatKnowledgeDate(source.updatedAt)} />
        </CardContent>
      </Card>
      <Tabs defaultValue="revisions">
        <TabsList className="flex w-full overflow-x-auto">
          <TabsTrigger value="revisions">Revisions</TabsTrigger>
          <TabsTrigger value="chunks">Chunks</TabsTrigger>
          <TabsTrigger value="evidence">Evidence</TabsTrigger>
          <TabsTrigger value="ingestion">Ingestion</TabsTrigger>
        </TabsList>
        <TabsContent value="revisions" className="grid gap-4 lg:grid-cols-[1fr_1fr]">
          <Card>
            <CardHeader><CardTitle>Revision history</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              {source.revisions.map((revision) => (
                <div key={revision.id} className="rounded-md border p-3">
                  <div className="flex items-center justify-between gap-2">
                    <div className="font-medium">Revision {revision.revisionNumber}</div>
                    {revision.id === source.currentRevisionId ? <Badge>Current</Badge> : <Badge variant="outline">Historical</Badge>}
                  </div>
                  <div className="mt-1 text-sm text-muted-foreground">{revision.contentHash} / {formatKnowledgeDate(revision.createdAt)}</div>
                  <div className="mt-2 flex gap-2 text-xs"><StatusBadge value={revision.parseStatus} /><StatusBadge value={revision.indexStatus} /></div>
                </div>
              ))}
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle>Revision diff</CardTitle><CardDescription>UNCHANGED / ADDED / REMOVED / MODIFIED / MOVED changes.</CardDescription></CardHeader>
            <CardContent className="space-y-2">
              {source.diff.length === 0 ? <EmptyState title="No revision diff for this source" /> : source.diff.map((item) => (
                <div key={item.id} className="rounded-md border p-3">
                  <StatusBadge value={item.changeType} />
                  <p className="mt-2 text-sm">{item.summary}</p>
                </div>
              ))}
            </CardContent>
          </Card>
        </TabsContent>
        <TabsContent value="chunks" className="grid gap-3">
          {source.revisions.flatMap((revision) => revision.chunks).map((chunk) => (
            <Card key={chunk.id} className="gap-3 py-4">
              <CardContent className="space-y-2 px-4">
                <div className="flex items-center justify-between"><Badge variant="outline">Chunk {chunk.chunkIndex}</Badge><span className="text-xs text-muted-foreground">{chunk.tokenCount} tokens</span></div>
                <p className="text-sm">{chunk.content}</p>
                <p className="text-xs text-muted-foreground">{chunk.sectionPath.join(" / ")} {chunk.pageNumber ? `/ page ${chunk.pageNumber}` : ""}</p>
              </CardContent>
            </Card>
          ))}
        </TabsContent>
        <TabsContent value="evidence" className="grid gap-3 md:grid-cols-2">
          {citations.map((citation) => <CitationButton key={citation.citationId} citation={citation} onOpenCitation={onOpenCitation} />)}
        </TabsContent>
        <TabsContent value="ingestion" className="grid gap-3">
          {source.latestJobId ? <JobProgressCard job={dataset.jobs.find((job) => job.job_id === source.latestJobId)!} events={dataset.jobEvents[source.latestJobId] ?? []} /> : <EmptyState title="No ingestion job recorded" />}
        </TabsContent>
      </Tabs>
    </div>
  );
}

function SearchView({ dataset, onOpenCitation }: { dataset: KnowledgeWorkspaceDataset; onOpenCitation: (citation: KnowledgeCitation) => void }) {
  const [query, setQuery] = useState("storage rollout");
  const [loading, setLoading] = useState(false);
  const results = searchKnowledge(dataset, query);
  function runSearch() {
    setLoading(true);
    window.setTimeout(() => setLoading(false), 250);
  }
  return (
    <div className="grid gap-4">
      <Card>
        <CardHeader><CardTitle>Hybrid retrieval</CardTitle><CardDescription>Lexical, Vector, Graph, and Fused Result channels are shown only when present in the response.</CardDescription></CardHeader>
        <CardContent className="space-y-3">
          <div className="grid gap-2 md:grid-cols-[1fr_auto]">
            <Input aria-label="Knowledge search query" value={query} onChange={(event) => setQuery(event.target.value)} />
            <Button onClick={runSearch} disabled={loading}>{loading ? <Loader2Icon className="size-4 animate-spin" /> : <SearchIcon className="size-4" />} Search</Button>
          </div>
          <div className="flex flex-wrap gap-2 text-sm text-muted-foreground"><FilterIcon className="size-4" /> Source, type, time, and entity filters are ready for Gateway integration.</div>
        </CardContent>
      </Card>
      {loading ? <Skeleton className="h-48" /> : results.length === 0 ? <EmptyState title="No evidence matched the query" /> : (
        <div className="grid gap-3">
          <div className="text-sm text-muted-foreground">{formatKnowledgeCount(results.length, "result")}</div>
          {results.map((result) => (
            <Card key={result.id}>
              <CardHeader><CardTitle>{result.title}</CardTitle><CardDescription>{result.retrievalChannels.join(" / ")}</CardDescription></CardHeader>
              <CardContent className="space-y-3">
                <p>{result.snippet}</p>
                <CitationRow citationIds={result.citationIds} dataset={dataset} onOpenCitation={onOpenCitation} />
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

function AnalysisView({ dataset, onOpenCitation }: { dataset: KnowledgeWorkspaceDataset; onOpenCitation: (citation: KnowledgeCitation) => void }) {
  const [query, setQuery] = useState(dataset.analysis.query);
  const [isRunning, setRunning] = useState(false);
  return (
    <div className="grid gap-4">
      <Card>
        <CardHeader><CardTitle>Evidence-grounded analysis</CardTitle><CardDescription>Structured output separates supported facts, inference, unsupported claims, and unresolved questions.</CardDescription></CardHeader>
        <CardContent className="space-y-3">
          <Textarea aria-label="Analysis question" value={query} onChange={(event) => setQuery(event.target.value)} />
          <div className="flex gap-2">
            <Button onClick={() => { setRunning(true); window.setTimeout(() => setRunning(false), 300); }} disabled={isRunning}>{isRunning ? <Loader2Icon className="size-4 animate-spin" /> : <RefreshCwIcon className="size-4" />} Re-analyze</Button>
            <Button variant="outline" onClick={() => void navigator.clipboard?.writeText(dataset.artifacts[0]?.markdown ?? dataset.analysis.answer)}>Copy Markdown</Button>
          </div>
        </CardContent>
      </Card>
      {isRunning ? <Skeleton className="h-72" /> : (
        <div className="grid gap-4 xl:grid-cols-2">
          <AnalysisSection title="Supported Facts" tone="success" items={dataset.analysis.supportedFacts.map((item) => ({ body: item.statement, meta: `${Math.round(item.confidence * 100)}% confidence`, citationIds: item.citationIds }))} dataset={dataset} onOpenCitation={onOpenCitation} />
          <AnalysisSection title="Inferred Conclusions" tone="warning" items={dataset.analysis.inferredConclusions.map((item) => ({ body: item.statement, meta: item.reasoningSummary, citationIds: item.citationIds }))} dataset={dataset} onOpenCitation={onOpenCitation} />
          <AnalysisSection title="Unsupported Claims" tone="danger" items={dataset.analysis.unsupportedClaims.map((item) => ({ body: item.statement, meta: item.reason, citationIds: [] }))} dataset={dataset} onOpenCitation={onOpenCitation} />
          <AnalysisSection title="Unresolved Questions" tone="neutral" items={dataset.analysis.unresolvedQuestions.map((item) => ({ body: item.question, meta: `${item.whyUnresolved} Needed: ${item.neededEvidence}`, citationIds: [] }))} dataset={dataset} onOpenCitation={onOpenCitation} />
        </div>
      )}
    </div>
  );
}

function GraphView({ dataset, onOpenCitation }: { dataset: KnowledgeWorkspaceDataset; onOpenCitation: (citation: KnowledgeCitation) => void }) {
  const [selectedId, setSelectedId] = useState(dataset.graph.nodes[0]?.id);
  const [kind, setKind] = useState("all");
  const nodes = dataset.graph.nodes.filter((node) => kind === "all" || node.kind === kind);
  const selected = dataset.graph.nodes.find((node) => node.id === selectedId) ?? nodes[0];
  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_320px]">
      <Card>
        <CardHeader>
          <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
            <div><CardTitle>Knowledge graph</CardTitle><CardDescription>Entity, Claim, Source, Evidence nodes with relation edges.</CardDescription></div>
            <Select value={kind} onValueChange={setKind}>
              <SelectTrigger className="w-44" aria-label="Filter graph node type"><SelectValue /></SelectTrigger>
              <SelectContent>{["all", "entity", "claim", "source", "evidence"].map((item) => <SelectItem key={item} value={item}>{item}</SelectItem>)}</SelectContent>
            </Select>
          </div>
        </CardHeader>
        <CardContent>
          <div className="overflow-auto rounded-md border bg-muted/20">
            <svg viewBox="0 0 760 440" role="img" aria-label="Knowledge graph showing entities, claims, sources and evidence" className="h-[440px] min-w-[760px]">
              {dataset.graph.edges.map((edge) => {
                const source = dataset.graph.nodes.find((node) => node.id === edge.source);
                const target = dataset.graph.nodes.find((node) => node.id === edge.target);
                if (!source || !target) return null;
                return <g key={edge.id}><line x1={source.x} y1={source.y} x2={target.x} y2={target.y} stroke="currentColor" className="text-border" strokeWidth="2" /><text x={(source.x + target.x) / 2} y={(source.y + target.y) / 2 - 6} className="fill-muted-foreground text-[10px]">{edge.label}</text></g>;
              })}
              {nodes.map((node) => (
                <g key={node.id}>
                  <button type="button" aria-label={`Select ${node.label}`} onClick={() => setSelectedId(node.id)}>
                    <circle cx={node.x} cy={node.y} r={node.id === selected?.id ? 34 : 28} className={cn("fill-background stroke-border", node.id === selected?.id && "stroke-primary")} strokeWidth="2" />
                    <text x={node.x} y={node.y + 46} textAnchor="middle" className="fill-foreground text-[12px]">{node.label}</text>
                  </button>
                </g>
              ))}
            </svg>
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>Node detail</CardTitle><CardDescription>Search, expand neighbors, fit view and reset are UI-ready; production graph expansion needs a Gateway contract.</CardDescription></CardHeader>
        <CardContent className="space-y-3">
          {selected ? <>
            <StatusBadge value={selected.kind} />
            <div className="font-medium">{selected.label}</div>
            <p className="text-sm text-muted-foreground">{selected.detail}</p>
            <CitationRow citationIds={selected.citationIds ?? []} dataset={dataset} onOpenCitation={onOpenCitation} />
            <div className="grid grid-cols-2 gap-2"><Button variant="outline" disabled>Expand</Button><Button variant="outline">Reset</Button></div>
          </> : <EmptyState title="Select a graph node" />}
        </CardContent>
      </Card>
    </div>
  );
}

function ConflictsView({ dataset, onOpenCitation }: { dataset: KnowledgeWorkspaceDataset; onOpenCitation: (citation: KnowledgeCitation) => void }) {
  const [classification, setClassification] = useState("all");
  const conflicts = dataset.conflicts.filter((conflict) => classification === "all" || conflict.classification === classification);
  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap gap-2">
        <Select value={classification} onValueChange={setClassification}>
          <SelectTrigger className="w-72" aria-label="Filter conflict classification"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All classifications</SelectItem>
            {["DIRECT_CONTRADICTION", "TEMPORAL_UPDATE", "SCOPE_OR_CONDITION_DIFFERENCE", "SOURCE_DISAGREEMENT", "POSSIBLE_CONFLICT", "INSUFFICIENT_EVIDENCE"].map((item) => <SelectItem key={item} value={item}>{item}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>
      {conflicts.map((conflict) => <ConflictSummary key={conflict.id} conflict={conflict} dataset={dataset} onOpenCitation={onOpenCitation} expanded />)}
    </div>
  );
}

function WorkflowsView({ dataset, demoMode = true }: { dataset: KnowledgeWorkspaceDataset; demoMode?: boolean }) {
  const [type, setType] = useState<WorkflowType>("decision_memo");
  return (
    <div className="grid gap-4 xl:grid-cols-[340px_1fr]">
      <Card>
        <CardHeader><CardTitle>Create workflow</CardTitle><CardDescription>Seven workflow types are represented; actions depend on real Gateway capability.</CardDescription></CardHeader>
        <CardContent className="space-y-3">
          <Select value={type} onValueChange={(value) => setType(value as WorkflowType)}>
            <SelectTrigger aria-label="Workflow type"><SelectValue /></SelectTrigger>
            <SelectContent>{Object.entries(workflowTypeLabels).map(([key, label]) => <SelectItem key={key} value={key}>{label}</SelectItem>)}</SelectContent>
          </Select>
          <Input aria-label="Workflow objective" defaultValue="Prepare rollout decision" />
          <Button disabled={!demoMode} onClick={() => toast.success(`${workflowTypeLabels[type]} accepted in demo`)}><PlayIcon className="size-4" /> Create workflow</Button>
          <p className="text-xs text-muted-foreground">Knowledge-to-Action creates an action draft only. Execution stays behind approval.</p>
        </CardContent>
      </Card>
      <div className="grid gap-4">
        {dataset.workflows.map((workflow) => (
          <Card key={workflow.id}>
            <CardHeader><CardTitle>{workflow.title}</CardTitle><CardDescription>{workflowTypeLabels[workflow.workflowType]} / {formatKnowledgeDate(workflow.updatedAt)}</CardDescription></CardHeader>
            <CardContent className="space-y-3">
              <div className="flex flex-wrap gap-2"><StatusBadge value={workflow.status} />{workflow.currentStep ? <Badge variant="outline">Current: {workflow.currentStep}</Badge> : null}</div>
              <div className="grid gap-2">
                {workflow.steps.map((step) => <WorkflowStepRow key={step.key} step={step} />)}
              </div>
              <div className="flex flex-wrap gap-2">
                <Button size="sm" variant="outline" disabled={workflow.status === "SUCCEEDED"}><PauseIcon className="size-4" /> Pause</Button>
                <Button size="sm" variant="outline" disabled={workflow.status !== "PAUSED"}><PlayIcon className="size-4" /> Resume</Button>
                <Button size="sm" variant="outline"><RefreshCwIcon className="size-4" /> Retry</Button>
                <Button size="sm" variant="outline" disabled>Generate artifact</Button>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

function ArtifactsView({ dataset, onOpenCitation }: { dataset: KnowledgeWorkspaceDataset; onOpenCitation: (citation: KnowledgeCitation) => void }) {
  const [selectedId, setSelectedId] = useState(dataset.artifacts[0]?.id);
  const selected = dataset.artifacts.find((artifact) => artifact.id === selectedId);
  return (
    <div className="grid gap-4 xl:grid-cols-[360px_1fr]">
      <Card>
        <CardHeader><CardTitle>Artifacts</CardTitle><CardDescription>Workflow outputs with provenance and stale status.</CardDescription></CardHeader>
        <CardContent className="space-y-2">
          {dataset.artifacts.map((artifact) => (
            <button key={artifact.id} type="button" onClick={() => setSelectedId(artifact.id)} className={cn("w-full rounded-md border p-3 text-left transition hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring", selectedId === artifact.id && "bg-accent")}>
              <div className="font-medium">{artifact.title}</div>
              <div className="mt-1 flex gap-2"><StatusBadge value={artifact.artifactType} /><StatusBadge value={artifact.stalenessStatus} /></div>
            </button>
          ))}
        </CardContent>
      </Card>
      {selected ? <ArtifactDetail artifact={selected} dataset={dataset} onOpenCitation={onOpenCitation} /> : <EmptyState title="Select an artifact" />}
    </div>
  );
}

function ApprovalsView({ dataset, demoMode = true }: { dataset: KnowledgeWorkspaceDataset; demoMode?: boolean }) {
  return (
    <div className="grid gap-4">
      <Alert>
        <ShieldCheckIcon className="size-4" />
        <AlertTitle>Approval chain</AlertTitle>
        <AlertDescription>
          Action Draft {"->"} Approval Request {"->"} Approved / Rejected {"->"} Action Execution {"->"} Succeeded / Failed / Reconciliation Required.
        </AlertDescription>
      </Alert>
      {dataset.approvals.map((approval) => (
        <Card key={approval.id}>
          <CardHeader><CardTitle>{approval.actionType}</CardTitle><CardDescription>{approval.payloadSummary}</CardDescription></CardHeader>
          <CardContent className="space-y-3">
            <div className="flex flex-wrap gap-2"><StatusBadge value={approval.status} /><StatusBadge value={approval.executionStatus ?? "PENDING"} /><RiskBadge risk={approval.riskLevel} /></div>
            <div className="grid gap-2 md:grid-cols-3"><Meta label="Payload hash" value={approval.payloadHash} /><Meta label="Requested by" value={approval.requestedBy} /><Meta label="Created" value={formatKnowledgeDate(approval.createdAt)} /></div>
            <div className="rounded-md border p-3 text-sm">{approval.audit.map((item) => <div key={item}>{item}</div>)}</div>
            <div className="flex flex-wrap gap-2">
              <Button size="sm" disabled={!demoMode || approval.status !== "AWAITING_APPROVAL"} onClick={() => toast.success("Demo approval recorded")}>Approve</Button>
              <Button size="sm" variant="outline" disabled={!demoMode || approval.status !== "AWAITING_APPROVAL"} onClick={() => toast.info("Demo rejection recorded")}>Reject</Button>
              <Button size="sm" variant="outline" disabled={approval.status !== "APPROVED" || approval.executionStatus === "SUCCEEDED"}>Execute fake action</Button>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function ActivityView({ dataset }: { dataset: KnowledgeWorkspaceDataset }) {
  const [type, setType] = useState("all");
  const events = dataset.activity.filter((event) => type === "all" || event.type === type);
  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
          <div><CardTitle>Activity</CardTitle><CardDescription>Unified view of available jobs, workflows, artifacts, approvals, actions, and updates.</CardDescription></div>
          <Select value={type} onValueChange={setType}>
            <SelectTrigger className="w-48" aria-label="Filter activity type"><SelectValue /></SelectTrigger>
            <SelectContent>{["all", "ingestion", "workflow", "artifact", "approval", "action", "update"].map((item) => <SelectItem key={item} value={item}>{item}</SelectItem>)}</SelectContent>
          </Select>
        </div>
      </CardHeader>
      <CardContent><ActivityList events={events} /></CardContent>
    </Card>
  );
}

function JobProgressCard({ job, events }: { job: KnowledgeWorkspaceDataset["jobs"][number]; events: KnowledgeWorkspaceDataset["jobEvents"][string] }) {
  const percent = typeof job.progress.percent === "number" ? job.progress.percent : job.status === "SUCCEEDED" ? 100 : 25;
  const stage = typeof job.progress.stage === "string" ? job.progress.stage : "queued";
  return (
    <div className="rounded-md border p-3">
      <div className="flex items-center justify-between gap-2"><div className="font-medium">{job.job_type}</div><StatusBadge value={job.status} /></div>
      <Progress value={percent} className="mt-3" />
      <div className="mt-2 text-sm text-muted-foreground">Attempt {job.attempt}/{job.max_attempts} / {stage}</div>
      {job.error_message ? <p className="mt-2 text-sm text-destructive">{job.error_message}</p> : null}
      <div className="mt-3 space-y-1 text-xs text-muted-foreground">
        {events.map((event) => <div key={event.event_id}>{formatKnowledgeDate(event.created_at)} - {event.event_type}</div>)}
      </div>
      {!["SUCCEEDED", "FAILED", "CANCELLED"].includes(job.status) ? <Button size="sm" variant="outline" className="mt-3"><XCircleIcon className="size-4" /> Cancel</Button> : null}
    </div>
  );
}

function StatusBadge({ value }: { value: string }) {
  const upper = value.toUpperCase();
  const destructive = ["FAILED", "STALE", "REJECTED", "CANCELLED", "INVALID"].includes(upper);
  const success = ["SUCCEEDED", "ACTIVE", "VALID", "CURRENT", "APPROVED"].includes(upper);
  return <Badge variant={destructive ? "destructive" : success ? "secondary" : "outline"} className="rounded-md">{value}</Badge>;
}

function RiskBadge({ risk }: { risk: string }) {
  return <Badge variant={risk === "HIGH" ? "destructive" : "outline"} className="rounded-md">Risk: {risk}</Badge>;
}

function CitationButton({ citation, onOpenCitation }: { citation: KnowledgeCitation; onOpenCitation: (citation: KnowledgeCitation) => void }) {
  return (
    <button type="button" onClick={() => onOpenCitation(citation)} className="rounded-md border p-3 text-left transition hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring">
      <div className="flex items-center gap-2"><Badge variant={citation.role === "direct" ? "secondary" : "outline"}>{citation.role === "direct" ? "Direct evidence" : "Parent context"}</Badge><span className="text-xs text-muted-foreground">{citation.sourceTitle}</span></div>
      <p className="mt-2 text-sm">&ldquo;{citation.quotedText}&rdquo;</p>
    </button>
  );
}

function CitationRow({ citationIds, dataset, onOpenCitation }: { citationIds: string[]; dataset: KnowledgeWorkspaceDataset; onOpenCitation: (citation: KnowledgeCitation) => void }) {
  if (citationIds.length === 0) return <p className="text-sm text-muted-foreground">No direct citation available.</p>;
  return <div className="flex flex-wrap gap-2">{citationIds.map((id) => { const citation = dataset.citations.find((item) => item.citationId === id); return citation ? <Button key={id} size="sm" variant="outline" onClick={() => onOpenCitation(citation)}>{citation.role === "direct" ? "Evidence" : "Context"} {id}</Button> : null; })}</div>;
}

function CitationSheet({ citation, onOpenChange }: { citation: KnowledgeCitation | null; onOpenChange: (open: boolean) => void }) {
  return (
    <Sheet open={Boolean(citation)} onOpenChange={onOpenChange}>
      <SheetContent className="w-full sm:max-w-xl">
        <SheetHeader>
          <SheetTitle>Citation detail</SheetTitle>
          <SheetDescription>Source, revision, chunk, location, quote, and offsets.</SheetDescription>
        </SheetHeader>
        {citation ? (
          <div className="space-y-4 px-4">
            <CitationButton citation={citation} onOpenCitation={() => undefined} />
            <div className="grid gap-2 text-sm">
              <Meta label="Source" value={citation.sourceTitle} />
              <Meta label="Revision" value={citation.revisionId} />
              <Meta label="Chunk" value={citation.chunkId} />
              <Meta label="Location" value={[citation.pageNumber ? `page ${citation.pageNumber}` : undefined, citation.sheetName, citation.sectionPath?.join(" / ")].filter(Boolean).join(" / ") || "Not provided"} />
              <Meta label="Offsets" value={`${citation.startOffset}-${citation.endOffset}`} />
              <Meta label="Evidence role" value={citation.role === "direct" ? "Direct evidence" : "Parent context only"} />
            </div>
          </div>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}

function ConflictSummary({ conflict, dataset, onOpenCitation, expanded = false }: { conflict: KnowledgeConflict; dataset: KnowledgeWorkspaceDataset; onOpenCitation: (citation: KnowledgeCitation) => void; expanded?: boolean }) {
  const claims = claimsForConflict(dataset, conflict);
  return (
    <Card>
      <CardHeader><CardTitle>{conflict.summary}</CardTitle><CardDescription>{conflict.classification} / {formatKnowledgeDate(conflict.updatedAt)}</CardDescription></CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap gap-2"><StatusBadge value={conflict.status} /><Badge variant="outline">{conflict.scopeOrCondition}</Badge></div>
        {expanded ? <div className="grid gap-2 md:grid-cols-2">{claims.map((claim) => <div key={claim.id} className="rounded-md border p-3 text-sm"><div className="font-medium">{claim.status}</div><p className="mt-1">{claim.text}</p><CitationRow citationIds={claim.citationIds} dataset={dataset} onOpenCitation={onOpenCitation} /></div>)}</div> : null}
        <p className="text-sm text-muted-foreground">Recommended next step: {conflict.recommendedNextStep}</p>
      </CardContent>
    </Card>
  );
}

function ArtifactSummary({ artifact, dataset, onOpenCitation }: { artifact: KnowledgeArtifact; dataset: KnowledgeWorkspaceDataset; onOpenCitation: (citation: KnowledgeCitation) => void }) {
  return (
    <div className="rounded-md border p-3">
      <div className="flex items-center justify-between gap-2"><div className="font-medium">{artifact.title}</div><StatusBadge value={artifact.stalenessStatus} /></div>
      <p className="mt-2 text-sm text-muted-foreground">{artifact.markdown.split("\n")[1] ?? "Structured artifact"}</p>
      <CitationRow citationIds={artifact.citationIds.slice(0, 2)} dataset={dataset} onOpenCitation={onOpenCitation} />
    </div>
  );
}

function ArtifactDetail({ artifact, dataset, onOpenCitation }: { artifact: KnowledgeArtifact; dataset: KnowledgeWorkspaceDataset; onOpenCitation: (citation: KnowledgeCitation) => void }) {
  return (
    <Card>
      <CardHeader><CardTitle>{artifact.title}</CardTitle><CardDescription>{artifact.artifactType} / {formatKnowledgeDate(artifact.createdAt)}</CardDescription></CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap gap-2"><StatusBadge value={artifact.validationStatus} /><StatusBadge value={artifact.stalenessStatus} /></div>
        {artifact.staleReasons.length > 0 ? <Alert><AlertTriangleIcon className="size-4" /><AlertTitle>Stale impact</AlertTitle><AlertDescription>{artifact.staleReasons.join(" ")}</AlertDescription></Alert> : null}
        <pre className="whitespace-pre-wrap rounded-md border bg-muted/30 p-4 text-sm">{artifact.markdown}</pre>
        <CitationRow citationIds={artifact.citationIds} dataset={dataset} onOpenCitation={onOpenCitation} />
        <Button variant="outline">Download Markdown</Button>
      </CardContent>
    </Card>
  );
}

function WorkflowStepRow({ step }: { step: KnowledgeWorkspaceDataset["workflows"][number]["steps"][number] }) {
  return (
    <div className="grid gap-2 rounded-md border p-3 md:grid-cols-[180px_1fr_auto]">
      <div className="font-medium">{step.label}</div>
      <div className="text-sm text-muted-foreground">{step.outputSummary ?? step.inputSummary}{step.error ? ` / ${step.error}` : ""}</div>
      <StatusBadge value={step.status} />
    </div>
  );
}

function AnalysisSection({ title, tone, items, dataset, onOpenCitation }: { title: string; tone: "success" | "warning" | "danger" | "neutral"; items: Array<{ body: string; meta: string; citationIds: string[] }>; dataset: KnowledgeWorkspaceDataset; onOpenCitation: (citation: KnowledgeCitation) => void }) {
  return (
    <Card className={cn(tone === "danger" && "border-destructive/40", tone === "warning" && "border-amber-500/40")}>
      <CardHeader><CardTitle>{title}</CardTitle></CardHeader>
      <CardContent className="space-y-3">{items.map((item) => <div key={item.body} className="rounded-md border p-3"><p className="font-medium">{item.body}</p><p className="mt-1 text-sm text-muted-foreground">{item.meta}</p><CitationRow citationIds={item.citationIds} dataset={dataset} onOpenCitation={onOpenCitation} /></div>)}</CardContent>
    </Card>
  );
}

function ActivityList({ events }: { events: KnowledgeActivityEvent[] }) {
  return (
    <div className="space-y-2">
      {events.map((event) => (
        <div key={event.id} className="flex gap-3 rounded-md border p-3">
          <ActivityIcon className="mt-0.5 size-4 text-muted-foreground" />
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2"><span className="font-medium">{event.title}</span><StatusBadge value={event.status} /></div>
            <p className="text-sm text-muted-foreground">{event.detail}</p>
            <div className="mt-1 text-xs text-muted-foreground">{formatKnowledgeDate(event.createdAt)}</div>
          </div>
          {event.linkedHref ? <Link className="text-sm underline-offset-4 hover:underline" href={event.linkedHref}>Open</Link> : null}
        </div>
      ))}
    </div>
  );
}

function EmptyState({ title }: { title: string }) {
  return (
    <Empty className="min-h-40 border">
      <EmptyHeader>
        <EmptyMedia variant="icon"><BookOpenIcon /></EmptyMedia>
        <EmptyTitle>{title}</EmptyTitle>
        <EmptyDescription>No production data is invented for this state.</EmptyDescription>
      </EmptyHeader>
    </Empty>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return <div><div className="text-xs text-muted-foreground">{label}</div><div className="break-words text-sm font-medium">{value}</div></div>;
}
