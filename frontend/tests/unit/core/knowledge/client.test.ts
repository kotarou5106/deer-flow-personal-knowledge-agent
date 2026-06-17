import { describe, expect, test, vi } from "vitest";

import { createKnowledgeClient } from "@/core/knowledge/client";
import type { KnowledgeTransport } from "@/core/knowledge/types";

function transportReturning(value: unknown): KnowledgeTransport {
  return { request: vi.fn().mockResolvedValue(value) };
}

describe("Knowledge client", () => {
  test("creates ingestion jobs through the formal endpoint shape", async () => {
    const transport = transportReturning({
      job_id: "job-1",
      status: "QUEUED",
      status_url: "/api/knowledge/jobs/job-1",
      events_url: "/api/knowledge/jobs/job-1/events",
    });
    const client = createKnowledgeClient(transport);
    await expect(
      client.createIngestion({
        source_type: "text",
        source_uri: "memory://note",
        metadata: { title: "Note" },
      }),
    ).resolves.toMatchObject({ job_id: "job-1", status: "QUEUED" });
    expect(transport.request).toHaveBeenCalledWith(
      expect.objectContaining({ method: "POST", path: "/ingestions" }),
    );
  });

  test("rejects trusted identity fields from client payloads", async () => {
    const client = createKnowledgeClient(transportReturning({}));
    await expect(
      client.createIngestion({
        source_type: "text",
        source_uri: "memory://note",
        metadata: {},
        workspace_id: "workspace-1",
      } as never),
    ).rejects.toThrow("trusted field");
  });
});
