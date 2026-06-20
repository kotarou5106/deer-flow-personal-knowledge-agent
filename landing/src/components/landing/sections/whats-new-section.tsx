"use client";

import MagicBento, { type BentoCardProps } from "@/components/ui/magic-bento";
import { Section } from "../section";

const features: BentoCardProps[] = [
  { color: "#0a0a0a", label: "Lifecycle", title: "知识生命周期", description: "从资料进入到版本演进、产物生成和受控行动，保持完整链路。" },
  { color: "#0a0a0a", label: "Source", title: "来源摄取", description: "接收个人资料、笔记、项目记录和对话结论，并记录来源上下文。" },
  { color: "#0a0a0a", label: "Evidence", title: "证据化知识", description: "知识条目绑定引用、版本和更新时间，便于追溯与复核。" },
  { color: "#0a0a0a", label: "Workspace", title: "工作区管理", description: "在专属工作区中浏览、整理、修订和维护长期知识状态。" },
  { color: "#0a0a0a", label: "Output", title: "Artifact 输出", description: "生成报告、清单、知识卡片和行动计划等结构化产物。" },
  { color: "#0a0a0a", label: "Approval", title: "Approval Flow", description: "关键修改和外部动作先生成草稿，经确认后再进入执行流程。" },
  { color: "#0a0a0a", label: "Memory", title: "长期维护", description: "结合 PostgreSQL 和 pgvector，让个人知识工作区持续演进。" },
];

export function WhatsNewSection() {
  return (
    <Section title="核心能力" subtitle="覆盖摄取、证据、工作区、产物、审批与长期维护">
      <div className="flex w-full items-center justify-center px-4"><MagicBento data={features} /></div>
    </Section>
  );
}
