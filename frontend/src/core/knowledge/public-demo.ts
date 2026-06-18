export const knowledgePublicDemoLinks = {
  demo: "/workspace/knowledge",
  architecture: "#architecture",
  github: "https://github.com/kotarou5106/deer-flow-personal-knowledge-agent",
  project: "/knowledge",
} as const;

export const workspaceProjectIntroLink = {
  href: knowledgePublicDemoLinks.project,
  label: "项目介绍",
} as const;

export const knowledgeLandingNav = [
  { label: "项目概览", href: "#overview" },
  { label: "核心能力", href: "#capabilities" },
  { label: "系统架构", href: "#architecture" },
  { label: "验证结果", href: "#verification" },
  { label: "体验 Demo", href: knowledgePublicDemoLinks.demo },
  { label: "GitHub", href: knowledgePublicDemoLinks.github, external: true },
] as const;

export const knowledgeLandingHero = {
  badge: "生产化导向的全栈智能体系统",
  title: "个人知识智能体",
  subtitle: "Personal Knowledge Agent",
  primaryCta: "体验 Demo",
  architectureCta: "查看系统架构",
  lifecycleTitle: "知识生命周期",
  lifecycleSubtitle: "从资料来源到受控行动",
  lifecycleBadge: "可演示",
  lifecycleNote:
    "这不仅是上传资料后进行问答。知识版本的变化会继续影响冲突、工作流、过期产物和审批控制的行动。",
} as const;

export const knowledgeLifecycleComparison = {
  ordinaryRag: ["文档", "切分", "检索", "回答"],
  personalKnowledgeAgent: [
    "来源",
    "快照与版本",
    "实体、主张与证据",
    "混合检索",
    "分析",
    "冲突与更新",
    "工作流与产物",
    "审批与行动",
  ],
} as const;

export const knowledgeDifferentiators = [
  {
    title: "知识生命周期",
    description:
      "资料来源会沉淀为快照、版本、主张、正式产物（Artifact）和受控行动，而不是一次性聊天上下文。",
  },
  {
    title: "证据约束",
    description:
      "回答和分析始终绑定引用、置信度，并区分有证据支持的事实与推断。",
  },
  {
    title: "版本与冲突",
    description:
      "新的知识版本会与既有知识比较，让过期产物和冲突主张保持可见。",
  },
  {
    title: "持久化工作流",
    description:
      "知识处理可以形成可复查的工作流（Workflow）、决策备忘录（Decision Memo）和长期保留的产物。",
  },
  {
    title: "审批控制的行动",
    description:
      "外部行动会先形成草稿，经过审批（Approval）后，再通过可审计的适配器执行。",
  },
] as const;

export const knowledgeCapabilities = [
  {
    title: "来源摄取",
    description:
      "把文件、链接和项目资料作为可追溯来源导入，并保留快照与版本，而不是匿名文本块。",
    keywords: ["来源", "快照", "版本"],
  },
  {
    title: "证据化知识",
    description:
      "抽取实体、主张、引用和证据，让后续分析能够说明每个结论由什么支撑。",
    keywords: ["实体", "主张", "证据"],
  },
  {
    title: "混合检索",
    description:
      "结合语义检索与结构化知识表面，支持直接证据检索和有约束的分析。",
    keywords: ["pgvector", "结构化过滤", "证据检索"],
  },
  {
    title: "版本与冲突追踪",
    description:
      "识别有意义的差异，暴露知识冲突，并在来源变化后标记过期产物。",
    keywords: ["差异", "冲突", "过期产物"],
  },
  {
    title: "工作流与正式产物",
    description:
      "把知识处理转化为可持续推进的工作流，并生成决策备忘录等正式产物。",
    keywords: ["工作流", "决策备忘录", "正式产物"],
  },
  {
    title: "审批控制的行动",
    description:
      "从知识结论生成行动草稿，经过审批后再通过受控适配器执行，并留下审计线索。",
    keywords: ["审批", "行动草稿", "审计"],
  },
] as const;

export const knowledgeDemoStory = [
  "导入多个项目资料来源",
  "同一来源产生新的版本",
  "系统识别真实差异",
  "检测到一组知识冲突",
  "检索找到直接证据",
  "分析区分有证据支持的事实与推断",
  "工作流生成决策备忘录",
  "旧产物因知识变化被标记为过期",
  "行动草稿进入审批流程",
  "伪执行适配器完成受控执行",
] as const;

export const knowledgeDemoSafetyNotice =
  "公共 Demo 不会发送真实邮件，也不会创建真实日历事件。所有外部动作均通过伪执行适配器（Fake Action Adapter）完成。";

export const knowledgeArchitectureRuntime = [
  "Next.js 前端",
  "Nginx",
  "DeerFlow Gateway",
  "PostgreSQL + pgvector",
  "持久化知识任务",
  "独立 Knowledge Worker",
  "产物存储",
] as const;

export const knowledgeArchitectureFlow = [
  "来源摄取",
  "结构化抽取",
  "混合检索",
  "证据化分析",
  "版本与冲突",
  "工作流与产物",
  "审批与行动",
] as const;

export const knowledgeVerificationEvidence = [
  "前端测试：339 项通过",
  "知识模块测试：140 项通过，16 项跳过",
  "后端完整测试：4563 项通过，32 项跳过",
  "评估数据集：17 项通过，0 项失败",
  "Docker Compose 真实冒烟测试：通过",
  "PostgreSQL / pgvector 数据库迁移：通过",
  "独立 Worker 任务处理：通过",
] as const;
