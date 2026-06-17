import { describe, expect, test, vi } from "vitest";

import type { KnowledgeFrontendConfig } from "@/core/knowledge/config";
import {
  parseKnowledgeSseChunk,
  subscribeKnowledgeJobEvents,
} from "@/core/knowledge/sse";

const config: KnowledgeFrontendConfig = {
  gatewayBaseUrl: "",
  knowledgeApiBasePath: "/api/knowledge",
  demoMode: false,
  requestTimeoutMs: 1000,
  sse: { initialRetryMs: 1, maxRetryMs: 1, maxRetries: 1 },
  appEnvironment: "test",
};

function eventFrame(seq: number, eventType: string) {
  return `event: ${eventType}\nid: ${seq}\ndata: ${JSON.stringify({
    event_id: `event-${seq}`,
    job_id: "job-1",
    seq,
    event_type: eventType,
    payload: {},
    created_at: "2026-06-17T00:00:00.000Z",
  })}\n\n`;
}

describe("Knowledge SSE", () => {
  test("parses frames while ignoring heartbeat comments", () => {
    expect(parseKnowledgeSseChunk(": heartbeat\n\nevent: job_started\nid: 1\ndata: {}\n\n")).toEqual([
      { event: "job_started", id: "1", data: "{}" },
    ]);
  });

  test("streams events, advances the cursor, and closes on terminal event", async () => {
    const onEvent = vi.fn();
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(eventFrame(1, "job_started")));
        controller.enqueue(new TextEncoder().encode(eventFrame(2, "job_succeeded")));
        controller.close();
      },
    });
    const fetchFn = vi.fn().mockResolvedValue(
      new Response(stream, {
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
      }),
    );
    const closed = new Promise<void>((resolve) => {
      subscribeKnowledgeJobEvents({
        config,
        jobId: "job-1",
        fetchFn,
        onEvent,
        onClose: resolve,
      });
    });
    await closed;
    expect(onEvent).toHaveBeenCalledTimes(2);
    expect(fetchFn).toHaveBeenCalledWith(
      "/api/knowledge/jobs/job-1/events",
      expect.objectContaining({ credentials: "include" }),
    );
  });
});
