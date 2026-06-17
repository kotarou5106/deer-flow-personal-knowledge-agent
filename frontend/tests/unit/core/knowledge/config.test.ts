import { describe, expect, test, vi } from "vitest";

vi.mock("@/env", () => ({
  env: {
    NODE_ENV: "test",
    NEXT_PUBLIC_API_URL: "",
    NEXT_PUBLIC_STATIC_WEBSITE_ONLY: "false",
    NEXT_PUBLIC_KNOWLEDGE_API_BASE_PATH: undefined,
    NEXT_PUBLIC_KNOWLEDGE_DEMO_MODE: undefined,
    NEXT_PUBLIC_KNOWLEDGE_REQUEST_TIMEOUT_MS: undefined,
    NEXT_PUBLIC_KNOWLEDGE_SSE_INITIAL_RETRY_MS: undefined,
    NEXT_PUBLIC_KNOWLEDGE_SSE_MAX_RETRY_MS: undefined,
    NEXT_PUBLIC_KNOWLEDGE_SSE_MAX_RETRIES: undefined,
  },
}));

vi.mock("@/core/config", () => ({
  getBackendBaseURL: () => "https://gateway.example/",
}));

vi.mock("@/core/static-mode", () => ({
  isStaticWebsiteOnly: () => false,
}));

import {
  buildKnowledgeUrl,
  resolveKnowledgeFrontendConfig,
} from "@/core/knowledge/config";

describe("Knowledge frontend config", () => {
  test("resolves safe defaults from the existing gateway config", () => {
    const config = resolveKnowledgeFrontendConfig();
    expect(config).toMatchObject({
      gatewayBaseUrl: "https://gateway.example",
      knowledgeApiBasePath: "/api/knowledge",
      demoMode: false,
      requestTimeoutMs: 15000,
      appEnvironment: "test",
    });
    expect(config.sse).toEqual({
      initialRetryMs: 500,
      maxRetryMs: 5000,
      maxRetries: 6,
    });
  });

  test("builds relative URLs when the gateway base URL is empty", () => {
    const url = buildKnowledgeUrl(
      { gatewayBaseUrl: "", knowledgeApiBasePath: "/api/knowledge" },
      "/jobs/job-1",
      { after_seq: 3 },
    );
    expect(url).toBe("/api/knowledge/jobs/job-1?after_seq=3");
  });
});
