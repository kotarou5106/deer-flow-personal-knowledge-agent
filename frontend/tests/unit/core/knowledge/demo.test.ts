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
    ).resolves.toMatchObject({ job_id: "job-atlas-architecture-v1" });
    await expect(
      transport.request({ method: "GET", path: "/jobs/job-atlas-architecture-v1" }),
    ).resolves.toMatchObject({ status: "SUCCEEDED" });
    await expect(
      transport.request({ method: "GET", path: "/overview" }),
    ).resolves.toMatchObject({ stats: expect.any(Object) });
    await expect(
      transport.request({ method: "GET", path: "/sources/src-atlas-architecture/detail" }),
    ).resolves.toMatchObject({ source: expect.objectContaining({ id: "src-atlas-architecture" }) });
    await expect(
      transport.request({ method: "GET", path: "/workflows" }),
    ).resolves.toMatchObject({ data: expect.any(Array) });
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
