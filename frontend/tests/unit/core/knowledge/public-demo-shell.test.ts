import { beforeEach, describe, expect, test, vi } from "vitest";

const staticMode = vi.hoisted(() => ({ value: false }));
const knowledgeConfig = vi.hoisted(() => ({ demoMode: false }));

vi.mock("@/core/static-mode", () => ({
  isStaticWebsiteOnly: () => staticMode.value,
}));

vi.mock("@/core/knowledge/config", () => ({
  resolveKnowledgeFrontendConfig: () => knowledgeConfig,
}));

import {
  hiddenPublicKnowledgeDemoShellLabels,
  isPublicKnowledgeDemoShell,
  publicKnowledgeDemoShellLinks,
} from "@/core/knowledge/public-demo-shell";

describe("public Knowledge demo shell", () => {
  beforeEach(() => {
    staticMode.value = false;
    knowledgeConfig.demoMode = false;
  });

  test("shows only project introduction and knowledge workspace links", () => {
    expect(publicKnowledgeDemoShellLinks).toEqual([
      { href: "/knowledge", label: "项目介绍" },
      { href: "/workspace/knowledge", label: "知识工作区" },
    ]);
  });

  test("documents generic DeerFlow shell labels hidden in public demo mode", () => {
    expect(hiddenPublicKnowledgeDemoShellLabels).toEqual([
      "新对话",
      "演示对话",
      "对话",
      "智能体",
      "渠道",
      "设置和更多",
    ]);
  });

  test("enables public shell in static website mode", () => {
    staticMode.value = true;
    expect(isPublicKnowledgeDemoShell()).toBe(true);
  });

  test("enables public shell in knowledge demo mode", () => {
    knowledgeConfig.demoMode = true;
    expect(isPublicKnowledgeDemoShell()).toBe(true);
  });

  test("keeps normal DeerFlow shell when neither public demo flag is active", () => {
    expect(isPublicKnowledgeDemoShell()).toBe(false);
  });
});
