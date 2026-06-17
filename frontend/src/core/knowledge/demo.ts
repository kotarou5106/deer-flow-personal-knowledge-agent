import type { KnowledgeTransport, KnowledgeTransportRequest } from "./types";
import {
  type KnowledgeJob,
  type KnowledgeJobAccepted,
  type KnowledgeJobEvent,
} from "./types";
import { demoKnowledgeWorkspace, demoNow } from "./workspace-fixtures";

const now = demoNow;

export const demoKnowledgeJob: KnowledgeJob =
  demoKnowledgeWorkspace.jobs[0] ??
  {
    job_id: "demo-ingestion-job",
    workspace_id: "demo-workspace",
    job_type: "ingestion",
    status: "SUCCEEDED",
    payload_hash: "demo-payload-hash",
    idempotency_key: "demo-ingestion",
    attempt: 1,
    max_attempts: 3,
    progress: { percent: 100 },
    created_at: now,
    started_at: now,
    completed_at: now,
    error_type: null,
    error_message: null,
    result_reference: { source_id: "demo-source" },
  };

export const demoKnowledgeEvents: KnowledgeJobEvent[] =
  demoKnowledgeWorkspace.jobEvents[demoKnowledgeJob.job_id] ?? [];

function listEnvelope(data: unknown[], request: KnowledgeTransportRequest) {
  return {
    data,
    pagination: {
      limit: Number(request.query?.limit ?? 50),
      offset: Number(request.query?.offset ?? 0),
    },
  };
}

export class DemoKnowledgeTransport implements KnowledgeTransport {
  async request(request: KnowledgeTransportRequest): Promise<unknown> {
    if (request.method === "POST" && request.path === "/ingestions") {
      return {
        job_id: demoKnowledgeJob.job_id,
        status: "QUEUED",
        status_url: `/api/knowledge/jobs/${demoKnowledgeJob.job_id}`,
        events_url: `/api/knowledge/jobs/${demoKnowledgeJob.job_id}/events`,
      } satisfies KnowledgeJobAccepted;
    }
    if (request.method === "GET" && request.path.startsWith("/jobs/")) {
      const jobId = request.path.split("/").at(-1);
      return (
        demoKnowledgeWorkspace.jobs.find((job) => job.job_id === jobId) ??
        demoKnowledgeJob
      );
    }
    if (
      request.method === "POST" &&
      (request.path.includes("/cancel") || request.path.includes("/retry"))
    ) {
      return {
        job_id: demoKnowledgeJob.job_id,
        status: "QUEUED",
        status_url: `/api/knowledge/jobs/${demoKnowledgeJob.job_id}`,
        events_url: `/api/knowledge/jobs/${demoKnowledgeJob.job_id}/events`,
      } satisfies KnowledgeJobAccepted;
    }
    if (request.method === "GET" && request.path === "/activity") {
      return listEnvelope(demoKnowledgeWorkspace.activity, request);
    }
    if (request.method === "GET" && request.path === "/overview") {
      return {
        stats: {
          sources: demoKnowledgeWorkspace.sources.length,
          revisions: demoKnowledgeWorkspace.sources.reduce(
            (count, source) => count + source.revisions.length,
            0,
          ),
          claims: demoKnowledgeWorkspace.claims.length,
          entities: demoKnowledgeWorkspace.entities.length,
          relations: demoKnowledgeWorkspace.relations.length,
          conflicts: demoKnowledgeWorkspace.conflicts.length,
          workflows: demoKnowledgeWorkspace.workflows.length,
          artifacts: demoKnowledgeWorkspace.artifacts.length,
          approvals: demoKnowledgeWorkspace.approvals.length,
        },
        recent_sources: demoKnowledgeWorkspace.sources.slice(0, 5),
        running_jobs: demoKnowledgeWorkspace.jobs.filter((job) => job.status === "RUNNING"),
        recent_artifacts: demoKnowledgeWorkspace.artifacts.slice(0, 5),
        pending_approvals: demoKnowledgeWorkspace.approvals.filter(
          (approval) => approval.status === "AWAITING_APPROVAL",
        ),
      };
    }
    if (request.method === "GET" && request.path === "/sources") {
      return listEnvelope(demoKnowledgeWorkspace.sources, request);
    }
    if (request.method === "GET" && request.path.startsWith("/sources/")) {
      const parts = request.path.split("/");
      const sourceId = parts[2];
      const source = demoKnowledgeWorkspace.sources.find((item) => item.id === sourceId);
      if (parts[3] === "revisions") {
        return listEnvelope(source?.revisions ?? [], request);
      }
      if (parts[3] === "detail") {
        return {
          source: source ?? {},
          revisions: source?.revisions ?? [],
          chunks: source?.revisions.flatMap((revision) => revision.chunks) ?? [],
          claims: demoKnowledgeWorkspace.claims,
          relations: demoKnowledgeWorkspace.relations,
          evidence: demoKnowledgeWorkspace.citations,
          jobs: demoKnowledgeWorkspace.jobs.filter((job) => job.job_id === source?.latestJobId),
        };
      }
      return source ?? {};
    }
    if (request.method === "GET" && request.path.startsWith("/revisions/")) {
      const revisionId = request.path.split("/").at(-1);
      return (
        demoKnowledgeWorkspace.sources
          .flatMap((source) => source.revisions)
          .find((revision) => revision.id === revisionId) ?? {}
      );
    }
    if (request.method === "GET" && request.path === "/claims") {
      return { data: demoKnowledgeWorkspace.claims };
    }
    if (request.method === "GET" && request.path === "/conflicts") {
      return { data: demoKnowledgeWorkspace.conflicts };
    }
    if (request.method === "POST" && request.path === "/search") {
      return { data: demoKnowledgeWorkspace.searchResults };
    }
    if (request.method === "POST" && request.path === "/analyses") {
      return {
        job_id: "demo-analysis-job",
        status: "SUCCEEDED",
        status_url: "/api/knowledge/jobs/demo-analysis-job",
        events_url: "/api/knowledge/jobs/demo-analysis-job/events",
      } satisfies KnowledgeJobAccepted;
    }
    if (request.method === "POST" && request.path === "/workflows") {
      return demoKnowledgeWorkspace.workflows[0] ?? {};
    }
    if (request.method === "GET" && request.path === "/workflows") {
      return listEnvelope(demoKnowledgeWorkspace.workflows, request);
    }
    if (request.method === "GET" && request.path.startsWith("/workflows/")) {
      const workflowId = request.path.split("/")[2];
      return demoKnowledgeWorkspace.workflows.find((workflow) => workflow.id === workflowId) ?? {};
    }
    if (request.method === "GET" && request.path === "/artifacts") {
      return listEnvelope(demoKnowledgeWorkspace.artifacts, request);
    }
    if (request.method === "GET" && request.path.startsWith("/artifacts/")) {
      const artifactId = request.path.split("/").at(-1);
      return demoKnowledgeWorkspace.artifacts.find((artifact) => artifact.id === artifactId) ?? {};
    }
    if (request.method === "GET" && request.path === "/approvals") {
      return listEnvelope(demoKnowledgeWorkspace.approvals, request);
    }
    if (request.method === "GET" && request.path.startsWith("/approvals/")) {
      const approvalId = request.path.split("/").at(-1);
      return demoKnowledgeWorkspace.approvals.find((approval) => approval.id === approvalId) ?? {};
    }
    if (request.method === "POST" && request.path.includes("/decision")) {
      return { status: "APPROVED", demo: true };
    }
    if (request.method === "POST" && request.path.includes("/preview")) {
      return { preview: "Demo fake action preview", safe: true };
    }
    if (request.method === "POST" && request.path.includes("/execute")) {
      return { status: "SUCCEEDED", connector_type: "fake", demo: true };
    }
    return { data: [], pagination: { limit: 20, offset: 0 } };
  }
}

export function createDemoKnowledgeEventStream(afterSeq = 0): ReadableStream {
  return new ReadableStream({
    start(controller) {
      for (const event of demoKnowledgeEvents.filter(
        (item) => item.seq > afterSeq,
      )) {
        controller.enqueue(
          new TextEncoder().encode(
            `event: ${event.event_type}\nid: ${event.seq}\ndata: ${JSON.stringify(event)}\n\n`,
          ),
        );
      }
      controller.close();
    },
  });
}
