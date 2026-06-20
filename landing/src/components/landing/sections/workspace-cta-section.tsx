import { AuroraText } from "@/components/ui/aurora-text";
import { Button } from "@/components/ui/button";
import { Section } from "../section";

export function WorkspaceCtaSection() {
  return (
    <Section
      title={<AuroraText colors={["#60A5FA", "#A5FA60", "#A560FA"]}>进入知识工作区</AuroraText>}
      subtitle="把项目资料、学习笔记和长期上下文沉淀到一个可持续管理的知识系统中。"
    >
      <div className="flex justify-center pt-4">
        <Button className="text-xl" size="lg" asChild>
          <a href="https://workspace.knowledge.kotarou.quest">打开知识工作区</a>
        </Button>
      </div>
    </Section>
  );
}
