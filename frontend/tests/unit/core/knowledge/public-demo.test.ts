import { describe, expect, test } from "vitest";

import {
  knowledgeArchitectureFlow,
  knowledgeArchitectureRuntime,
  knowledgeCapabilities,
  knowledgeDemoSafetyNotice,
  knowledgeDemoStory,
  knowledgeLandingHero,
  knowledgeLandingNav,
  knowledgeLifecycleComparison,
  knowledgePublicDemoLinks,
  knowledgeVerificationEvidence,
  workspaceProjectIntroLink,
} from "@/core/knowledge/public-demo";

describe("Knowledge public demo landing content", () => {
  test("uses Chinese-first hero copy while keeping the formal project name", () => {
    expect(knowledgeLandingHero).toMatchObject({
      badge: "生产化导向的全栈智能体系统",
      title: "个人知识智能体",
      subtitle: "Personal Knowledge Agent",
      primaryCta: "体验 Demo",
      architectureCta: "查看系统架构",
    });
  });

  test("points the primary demo entry at the Knowledge Workspace", () => {
    expect(knowledgePublicDemoLinks.demo).toBe("/workspace/knowledge");
    expect(knowledgeLandingNav).toContainEqual({
      label: "体验 Demo",
      href: "/workspace/knowledge",
    });
    expect(knowledgeLandingNav.map((item) => item.label)).toEqual([
      "项目概览",
      "核心能力",
      "系统架构",
      "验证结果",
      "体验 Demo",
      "GitHub",
    ]);
  });

  test("uses the configured public GitHub repository in a nav item", () => {
    expect(knowledgePublicDemoLinks.github).toBe(
      "https://github.com/kotarou5106/deer-flow-personal-knowledge-agent",
    );
    expect(knowledgeLandingNav).toContainEqual({
      label: "GitHub",
      href: knowledgePublicDemoLinks.github,
      external: true,
    });
  });

  test("keeps the ordinary RAG comparison distinct from the agent lifecycle", () => {
    expect(knowledgeLifecycleComparison.ordinaryRag).toEqual([
      "文档",
      "切分",
      "检索",
      "回答",
    ]);
    expect(knowledgeLifecycleComparison.personalKnowledgeAgent).toEqual([
      "来源",
      "快照与版本",
      "实体、主张与证据",
      "混合检索",
      "分析",
      "冲突与更新",
      "工作流与产物",
      "审批与行动",
    ]);
  });

  test("lists all six core capability groups", () => {
    expect(knowledgeCapabilities.map((capability) => capability.title)).toEqual([
      "来源摄取",
      "证据化知识",
      "混合检索",
      "版本与冲突追踪",
      "工作流与正式产物",
      "审批控制的行动",
    ]);
    expect(knowledgeCapabilities[2]?.keywords).toContain("pgvector");
    expect(knowledgeCapabilities[4]?.keywords).toContain("决策备忘录");
  });

  test("documents the demo story and fake action safety boundary", () => {
    expect(knowledgeDemoStory).toContain("行动草稿进入审批流程");
    expect(knowledgeDemoStory).toContain("伪执行适配器完成受控执行");
    expect(knowledgeDemoSafetyNotice).toContain("Fake Action Adapter");
    expect(knowledgeDemoSafetyNotice).toContain("不会发送真实邮件");
  });

  test("contains architecture and verification evidence sections", () => {
    expect(knowledgeArchitectureRuntime).toContain("Next.js 前端");
    expect(knowledgeArchitectureRuntime).toContain("独立 Knowledge Worker");
    expect(knowledgeArchitectureFlow).toContain("审批与行动");
    expect(knowledgeVerificationEvidence).toContain(
      "Docker Compose 真实冒烟测试：通过",
    );
    expect(knowledgeVerificationEvidence).toContain(
      "独立 Worker 任务处理：通过",
    );
  });

  test("provides a workspace return path to the public project introduction", () => {
    expect(workspaceProjectIntroLink).toEqual({
      href: "/knowledge",
      label: "项目介绍",
    });
  });
});
