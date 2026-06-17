import { describe, expect, test } from "vitest";

import { KnowledgeApiError } from "@/core/knowledge/errors";
import {
  knowledgeQueryKeys,
  shouldRetryKnowledgeQuery,
} from "@/core/knowledge/hooks";

describe("Knowledge hooks helpers", () => {
  test("builds stable query keys", () => {
    expect(knowledgeQueryKeys.all).toEqual(["knowledge"]);
    expect(knowledgeQueryKeys.job("job-1")).toEqual([
      "knowledge",
      "jobs",
      "job-1",
    ]);
  });

  test("does not retry non-retryable auth failures", () => {
    expect(
      shouldRetryKnowledgeQuery(
        0,
        new KnowledgeApiError({
          kind: "authentication",
          message: "Sign in",
        }),
      ),
    ).toBe(false);
    expect(shouldRetryKnowledgeQuery(0, new Error("network"))).toBe(true);
    expect(shouldRetryKnowledgeQuery(2, new Error("network"))).toBe(false);
  });
});
