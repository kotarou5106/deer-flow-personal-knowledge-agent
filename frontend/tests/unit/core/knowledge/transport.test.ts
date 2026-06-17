import { beforeEach, describe, expect, test, vi } from "vitest";

vi.mock("@/core/api/fetcher", () => ({
  isStateChangingMethod: (method: string) => method !== "GET",
  readCsrfCookie: () => "csrf-token",
}));

import type { KnowledgeFrontendConfig } from "@/core/knowledge/config";
import { GatewayKnowledgeTransport } from "@/core/knowledge/transport";

const config: KnowledgeFrontendConfig = {
  gatewayBaseUrl: "",
  knowledgeApiBasePath: "/api/knowledge",
  demoMode: false,
  requestTimeoutMs: 1000,
  sse: { initialRetryMs: 1, maxRetryMs: 1, maxRetries: 1 },
  appEnvironment: "test",
};

const fetchFn = vi.fn();

beforeEach(() => {
  fetchFn.mockReset();
});

describe("GatewayKnowledgeTransport", () => {
  test("sends JSON, credentials and CSRF for state-changing requests", async () => {
    fetchFn.mockResolvedValueOnce(
      new Response(JSON.stringify({ ok: true }), { status: 200 }),
    );
    const transport = new GatewayKnowledgeTransport(config, fetchFn);
    await transport.request({
      method: "POST",
      path: "/ingestions",
      body: { source_type: "text" },
    });
    expect(fetchFn).toHaveBeenCalledWith(
      "/api/knowledge/ingestions",
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        body: JSON.stringify({ source_type: "text" }),
      }),
    );
    const headers = fetchFn.mock.calls[0]?.[1]?.headers as Headers;
    expect(headers.get("X-CSRF-Token")).toBe("csrf-token");
    expect(headers.get("Content-Type")).toBe("application/json");
  });
});
