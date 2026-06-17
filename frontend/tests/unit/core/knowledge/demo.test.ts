import { describe, expect, test } from "vitest";

import {
  DemoKnowledgeTransport,
  createDemoKnowledgeEventStream,
  demoKnowledgeEvents,
} from "@/core/knowledge/demo";

describe("DemoKnowledgeTransport", () => {
  test("returns deterministic ingestion and job fixtures without network", async () => {
    const transport = new DemoKnowledgeTransport();
    await expect(
      transport.request({ method: "POST", path: "/ingestions" }),
    ).resolves.toMatchObject({ job_id: "demo-ingestion-job" });
    await expect(
      transport.request({ method: "GET", path: "/jobs/demo-ingestion-job" }),
    ).resolves.toMatchObject({ status: "SUCCEEDED" });
  });

  test("creates an ordered event stream that respects the cursor", async () => {
    const reader = createDemoKnowledgeEventStream(1).getReader();
    const chunks: string[] = [];
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      chunks.push(new TextDecoder().decode(value));
    }
    expect(chunks.join("")).toContain(demoKnowledgeEvents[1]!.event_id);
    expect(chunks.join("")).not.toContain(demoKnowledgeEvents[0]!.event_id);
  });
});
