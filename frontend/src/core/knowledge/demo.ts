import type { KnowledgeTransport, KnowledgeTransportRequest } from "./types";
import {
  type KnowledgeJob,
  type KnowledgeJobAccepted,
  type KnowledgeJobEvent,
} from "./types";

const now = "2026-06-17T00:00:00.000Z";

export const demoKnowledgeJob: KnowledgeJob = {
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

export const demoKnowledgeEvents: KnowledgeJobEvent[] = [
  {
    event_id: "demo-event-1",
    job_id: demoKnowledgeJob.job_id,
    seq: 1,
    event_type: "job_queued",
    payload: {},
    created_at: now,
  },
  {
    event_id: "demo-event-2",
    job_id: demoKnowledgeJob.job_id,
    seq: 2,
    event_type: "job_started",
    payload: {},
    created_at: now,
  },
  {
    event_id: "demo-event-3",
    job_id: demoKnowledgeJob.job_id,
    seq: 3,
    event_type: "job_succeeded",
    payload: { source_id: "demo-source" },
    created_at: now,
  },
];

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
    if (request.method === "GET" && request.path === "/jobs/demo-ingestion-job") {
      return demoKnowledgeJob;
    }
    if (
      request.method === "POST" &&
      (request.path === "/ingestions/demo-ingestion-job/cancel" ||
        request.path === "/ingestions/demo-ingestion-job/retry")
    ) {
      return {
        job_id: demoKnowledgeJob.job_id,
        status: "QUEUED",
        status_url: `/api/knowledge/jobs/${demoKnowledgeJob.job_id}`,
        events_url: `/api/knowledge/jobs/${demoKnowledgeJob.job_id}/events`,
      } satisfies KnowledgeJobAccepted;
    }
    if (request.method === "GET" && request.path === "/activity") {
      return { data: [demoKnowledgeJob], pagination: { limit: 20, offset: 0 } };
    }
    if (request.method === "GET" && request.path === "/sources") {
      return {
        data: [{ source_id: "demo-source", title: "Demo source" }],
        pagination: { limit: 20, offset: 0 },
      };
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
