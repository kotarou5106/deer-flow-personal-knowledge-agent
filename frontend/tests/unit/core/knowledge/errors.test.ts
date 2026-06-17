import { describe, expect, test } from "vitest";

import {
  KnowledgeApiError,
  classifyKnowledgeHttpError,
  normalizeKnowledgeResponseError,
} from "@/core/knowledge/errors";

describe("Knowledge errors", () => {
  test("classifies auth, csrf, validation and service configuration failures", () => {
    expect(classifyKnowledgeHttpError(401)).toBe("authentication");
    expect(classifyKnowledgeHttpError(403, "csrf_failed")).toBe("csrf");
    expect(classifyKnowledgeHttpError(422)).toBe("validation");
    expect(classifyKnowledgeHttpError(503, "service_not_configured")).toBe(
      "service_unavailable",
    );
  });

  test("normalizes structured backend errors without dropping request id", async () => {
    const error = await normalizeKnowledgeResponseError(
      new Response(
        JSON.stringify({
          detail: {
            error: {
              code: "service_not_configured",
              message: "Knowledge database is not configured.",
            },
          },
        }),
        {
          status: 503,
          headers: { "x-request-id": "request-1" },
        },
      ),
    );
    expect(error).toBeInstanceOf(KnowledgeApiError);
    expect(error).toMatchObject({
      kind: "service_unavailable",
      code: "service_not_configured",
      requestId: "request-1",
    });
  });
});
