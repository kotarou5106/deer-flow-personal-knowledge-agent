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

  test("creates synchronous analysis requests through the gateway contract", async () => {
    const transport = transportReturning({
      query: "What changed?",
      answer: "Supported by cited evidence.",
      model_identity: "deterministic-analysis",
    });
    const client = createKnowledgeClient(transport);

    await expect(client.createAnalysis({ query: "What changed?", context_budget: 5000 })).resolves.toMatchObject({
      model_identity: "deterministic-analysis",
    });
    expect(transport.request).toHaveBeenCalledWith(
      expect.objectContaining({
        method: "POST",
        path: "/analyses",
        body: {
          query: "What changed?",
          filters: {},
          context_budget: 5000,
          idempotency_key: null,
        },
      }),
    );
  });

  test("rejects trusted identity fields from analysis payloads", async () => {
    const client = createKnowledgeClient(transportReturning({}));

    await expect(
      client.createAnalysis({
        query: "hello",
        workspace_id: "workspace-1",
      } as never),
    ).rejects.toThrow("trusted field");
  });

  test("requests production overview through the gateway contract", async () => {
    const transport = transportReturning({
      stats: {},
      recent_sources: [],
      running_jobs: [],
      recent_artifacts: [],
      pending_approvals: [],
    });
    const client = createKnowledgeClient(transport);

    await expect(client.getOverview()).resolves.toMatchObject({ stats: {} });
    expect(transport.request).toHaveBeenCalledWith(
      expect.objectContaining({ method: "GET", path: "/overview" }),
    );
  });

  test("requests source detail through the gateway contract", async () => {
    const transport = transportReturning({
      source: { source_id: "source-1" },
      revisions: [],
      chunks: [],
      claims: [],
      relations: [],
      evidence: [],
      jobs: [],
    });
    const client = createKnowledgeClient(transport);

    await expect(client.getSourceDetail("source-1")).resolves.toMatchObject({
      source: { source_id: "source-1" },
    });
    expect(transport.request).toHaveBeenCalledWith(
      expect.objectContaining({
        method: "GET",
        path: "/sources/source-1/detail",
      }),
    );
  });

  test("lists workflows without creating a job", async () => {
    const transport = transportReturning({
      data: [],
      pagination: { limit: 20, offset: 3 },
    });
    const client = createKnowledgeClient(transport);

    await expect(client.listWorkflows({ limit: 20, offset: 3 })).resolves.toMatchObject({
      data: [],
    });
    expect(transport.request).toHaveBeenCalledWith(
      expect.objectContaining({
        method: "GET",
        path: "/workflows",
        query: { limit: 20, offset: 3 },
      }),
    );
  });
});
