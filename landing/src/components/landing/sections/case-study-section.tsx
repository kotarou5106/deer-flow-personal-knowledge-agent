import { Card } from "@/components/ui/card";
import { Section } from "../section";

const cases = [
  ["个人资料沉淀为可追溯知识", "把简历、项目记录、学习笔记和决策过程整理成带来源的知识条目。"],
  ["管理知识来源、版本和证据", "保留资料来源、更新时间和证据链，支持后续校验与回溯。"],
  ["生成结构化 Artifact", "将知识整理结果输出为报告、清单、卡片和工作说明等结构化产物。"],
  ["处理知识冲突和过期内容", "识别相互矛盾或已经过期的信息，并进入人工确认流程。"],
  ["审批后执行受控行动", "关键写入、修改和外部动作先生成草稿，经确认后再执行。"],
  ["长期维护个人知识工作区", "让个人知识、项目状态和后续行动在一个持续运行的工作区中演进。"],
] as const;

export function CaseStudySection() {
  return (
    <Section title="知识工作场景" subtitle="围绕个人资料、证据化知识和受控行动的长期工作流">
      <div className="container-md mt-8 grid grid-cols-1 gap-4 px-4 md:grid-cols-2 md:px-20 lg:grid-cols-3">
        {cases.map(([title, description], index) => (
          <Card key={title} className="relative h-56 cursor-default overflow-hidden border-white/10 bg-zinc-950/70 p-5">
            <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(96,165,250,0.18),transparent_38%),radial-gradient(circle_at_bottom_right,rgba(34,197,94,0.12),transparent_36%)]" />
            <div className="relative z-10 flex h-full flex-col justify-between">
              <div className="flex size-10 items-center justify-center rounded-md border border-white/10 bg-white/5 font-mono text-sm text-zinc-300">{String(index + 1).padStart(2, "0")}</div>
              <div className="space-y-3">
                <h3 className="text-xl font-bold text-white">{title}</h3>
                <p className="leading-7 text-zinc-400">{description}</p>
              </div>
            </div>
          </Card>
        ))}
      </div>
    </Section>
  );
}
