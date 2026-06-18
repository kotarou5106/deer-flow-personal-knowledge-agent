import type { KnowledgeJob, KnowledgeJobAccepted, KnowledgeJobEvent } from "./types";

export type KnowledgeSourceType = "pdf" | "docx" | "pptx" | "xlsx" | "markdown" | "txt" | "html" | "url";
export type KnowledgeSourceStatus = "ACTIVE" | "PARSING" | "INDEXING" | "FAILED" | "ARCHIVED";
export type RevisionChangeType = "UNCHANGED" | "ADDED" | "REMOVED" | "MODIFIED" | "MOVED";
export type EvidenceRole = "direct" | "parent_context";
export type ConflictClassification =
  | "DIRECT_CONTRADICTION"
  | "TEMPORAL_UPDATE"
  | "SCOPE_OR_CONDITION_DIFFERENCE"
  | "SOURCE_DISAGREEMENT"
  | "POSSIBLE_CONFLICT"
  | "INSUFFICIENT_EVIDENCE";
export type WorkflowStatus = "READY" | "PENDING" | "RUNNING" | "PAUSED" | "COMPLETED" | "REQUIRES_APPROVAL" | "SUCCEEDED" | "FAILED" | "CANCELLED";
export type ApprovalStatus = "DRAFT" | "AWAITING_APPROVAL" | "APPROVED" | "REJECTED" | "CANCELLED";
export type ActionExecutionStatus = "PENDING" | "EXECUTING" | "SUCCEEDED" | "FAILED" | "RECONCILIATION_REQUIRED";
export type ArtifactStalenessStatus = "CURRENT" | "STALE" | "UNKNOWN";
export type RiskLevel = "LOW" | "MEDIUM" | "HIGH";

export type KnowledgeCitation = {
  citationId: string;
  sourceId: string;
  revisionId: string;
  chunkId: string;
  evidenceSpanId: string;
  sourceTitle: string;
  sourceUri: string;
  quotedText: string;
  pageNumber?: number;
  slideNumber?: number;
  sheetName?: string;
  sectionPath?: string[];
  startOffset: number;
  endOffset: number;
  role: EvidenceRole;
};

export type KnowledgeChunk = {
  id: string;
  revisionId: string;
  parentChunkId?: string;
  chunkIndex: number;
  tokenCount: number;
  content: string;
  pageNumber?: number;
  sectionPath: string[];
  startOffset: number;
  endOffset: number;
};

export type KnowledgeRevision = {
  id: string;
  sourceId: string;
  revisionNumber: number;
  previousRevisionId?: string;
  contentHash: string;
  parseStatus: "PENDING" | "SUCCEEDED" | "FAILED";
  indexStatus: "PENDING" | "SUCCEEDED" | "FAILED";
  createdAt: string;
  chunks: KnowledgeChunk[];
};

export type RevisionDiffItem = {
  id: string;
  changeType: RevisionChangeType;
  oldChunkId?: string;
  newChunkId?: string;
  summary: string;
};

export type KnowledgeSource = {
  id: string;
  sourceType: KnowledgeSourceType;
  canonicalUri: string;
  title: string;
  author?: string;
  status: KnowledgeSourceStatus;
  currentRevisionId: string;
  latestJobId?: string;
  claimCount: number;
  chunkCount: number;
  updatedAt: string;
  error?: string;
  revisions: KnowledgeRevision[];
  diff: RevisionDiffItem[];
};

export type KnowledgeEntity = {
  id: string;
  canonicalName: string;
  entityType: string;
  aliases: string[];
  description: string;
};

export type KnowledgeClaim = {
  id: string;
  text: string;
  normalizedSubject: string;
  predicate: string;
  normalizedObject: string;
  stance: "SUPPORTS" | "CONTRADICTS" | "NEUTRAL";
  confidence: number;
  status: "CURRENT_ACTIVE" | "SUPERSEDED" | "HISTORICAL" | "PENDING_CONFLICT_REVIEW";
  validFrom?: string;
  validTo?: string;
  citationIds: string[];
};

export type KnowledgeRelation = {
  id: string;
  sourceEntityId: string;
  targetEntityId: string;
  relationType: string;
  confidence: number;
  citationId: string;
};

export type SearchResult = {
  id: string;
  title: string;
  snippet: string;
  sourceId: string;
  revisionId: string;
  citationIds: string[];
  retrievalChannels: Array<"Lexical" | "Vector" | "Graph" | "Fused Result">;
  relatedClaimIds: string[];
  relatedEntityIds: string[];
};

export type AnalysisResultDemo = {
  query: string;
  answer: string;
  supportedFacts: Array<{ statement: string; confidence: number; citationIds: string[] }>;
  inferredConclusions: Array<{ statement: string; confidence: number; reasoningSummary: string; citationIds: string[] }>;
  unsupportedClaims: Array<{ statement: string; reason: string; severity: string }>;
  unresolvedQuestions: Array<{ question: string; whyUnresolved: string; neededEvidence: string }>;
  sourceIds: string[];
};

export type GraphNode = {
  id: string;
  label: string;
  kind: "entity" | "claim" | "source" | "evidence";
  x: number;
  y: number;
  detail: string;
  citationIds?: string[];
};

export type GraphEdge = {
  id: string;
  source: string;
  target: string;
  label: string;
};

export type KnowledgeConflict = {
  id: string;
  classification: ConflictClassification;
  status: "UNRESOLVED" | "REVIEWED";
  summary: string;
  claimIds: string[];
  citationIds: string[];
  scopeOrCondition: string;
  activeClaimId: string;
  affectedArtifactIds: string[];
  recommendedNextStep: string;
  updatedAt: string;
};

export type WorkflowType =
  | "topic_dossier"
  | "project_context_pack"
  | "reading_synthesis"
  | "decision_memo"
  | "meeting_preparation"
  | "knowledge_update_review"
  | "knowledge_to_action";

export type KnowledgeWorkflowStep = {
  key: string;
  label: string;
  status: WorkflowStatus;
  inputSummary: string;
  outputSummary?: string;
  error?: string;
};

export type KnowledgeWorkflow = {
  id: string;
  workflowType: WorkflowType;
  title: string;
  status: WorkflowStatus;
  currentStep?: string;
  sourceIds: string[];
  artifactIds: string[];
  actionDraftId?: string;
  updatedAt: string;
  steps: KnowledgeWorkflowStep[];
};

export type KnowledgeArtifact = {
  id: string;
  artifactType: string;
  title: string;
  validationStatus: "PENDING" | "VALID" | "INVALID";
  stalenessStatus: ArtifactStalenessStatus;
  createdAt: string;
  workflowId?: string;
  sourceIds: string[];
  citationIds: string[];
  staleReasons: string[];
  markdown: string;
};

export type KnowledgeApproval = {
  id: string;
  workflowId: string;
  actionType: string;
  payloadSummary: string;
  payloadHash: string;
  requestedBy: string;
  riskLevel: RiskLevel;
  status: ApprovalStatus;
  executionStatus?: ActionExecutionStatus;
  createdAt: string;
  decidedAt?: string;
  audit: string[];
};

export type KnowledgeActivityEvent = {
  id: string;
  type: "ingestion" | "workflow" | "artifact" | "approval" | "action" | "update";
  status: string;
  title: string;
  linkedHref?: string;
  createdAt: string;
  detail: string;
};

export type KnowledgeWorkspaceDataset = {
  sources: KnowledgeSource[];
  citations: KnowledgeCitation[];
  entities: KnowledgeEntity[];
  claims: KnowledgeClaim[];
  relations: KnowledgeRelation[];
  jobs: KnowledgeJob[];
  jobEvents: Record<string, KnowledgeJobEvent[]>;
  searchResults: SearchResult[];
  analysis: AnalysisResultDemo;
  graph: { nodes: GraphNode[]; edges: GraphEdge[] };
  conflicts: KnowledgeConflict[];
  workflows: KnowledgeWorkflow[];
  artifacts: KnowledgeArtifact[];
  approvals: KnowledgeApproval[];
  activity: KnowledgeActivityEvent[];
};

export type KnowledgeImportDraft = {
  mode: "file" | "url";
  sourceUri: string;
  mediaType?: string | null;
  title?: string;
};

export type DemoImportResult = KnowledgeJobAccepted & {
  acceptedAt: string;
};
