export const workflowStages = [
  { title: "来源摄取", detail: "识别资料类型与项目上下文", file: "source-capture.md" },
  { title: "证据归档", detail: "绑定原始引用与证据片段", file: "evidence-archive.md" },
  { title: "知识版本", detail: "生成可追踪的版本记录", file: "knowledge-version.md" },
  { title: "冲突检查", detail: "标记矛盾、过期与待确认信息", file: "conflict-check.md" },
  { title: "Artifact", detail: "输出知识卡片、报告与行动清单", file: "artifact-output.md" },
  { title: "Approval Flow", detail: "关键修改经确认后进入受控行动", file: "approval-flow.md" },
] as const;

export const workflowArtifacts = ["knowledge-card.md", "decision-memo.md", "next-actions.md"] as const;
