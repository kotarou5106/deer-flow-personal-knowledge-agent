import { KnowledgeWorkflowDemo } from "../knowledge-workflow-demo";
import { Section } from "../section";

export function SkillsSection() {
  return (
    <Section className="w-full bg-white/2" title="知识工作流" subtitle="来源摄取 → 证据归档 → 知识版本 → 冲突检查 → Artifact 输出 → Approval Flow → 受控行动">
      <div className="relative mt-8 overflow-hidden"><KnowledgeWorkflowDemo /></div>
    </Section>
  );
}
