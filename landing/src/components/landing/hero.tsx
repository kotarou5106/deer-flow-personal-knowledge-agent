"use client";

import { ChevronRightIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { FlickeringGrid } from "@/components/ui/flickering-grid";
import Galaxy from "@/components/ui/galaxy";
import { cn } from "@/lib/utils";

export function Hero({ className }: { className?: string }) {
  return (
    <section className={cn("relative flex min-h-screen w-full flex-col items-center justify-center overflow-hidden", className)}>
      <div className="absolute inset-0 z-0 bg-black/40">
        <Galaxy mouseRepulsion={false} starSpeed={0.2} density={0.6} glowIntensity={0.35} twinkleIntensity={0.3} speed={0.5} />
      </div>
      <FlickeringGrid
        className="absolute inset-x-0 top-24 z-0 h-[70vh] opacity-45 [mask-image:radial-gradient(ellipse_at_center,black_0%,transparent_72%)]"
        squareSize={4}
        gridGap={4}
        color="white"
        maxOpacity={0.22}
        flickerChance={0.25}
      />
      <div className="container-md relative z-10 mx-auto flex min-h-screen flex-col items-center justify-center px-4 pt-16">
        <h1 className="bg-gradient-to-r from-white via-sky-100 to-emerald-200 bg-clip-text text-center text-4xl font-bold text-transparent md:text-6xl">
          个人知识 Agent
        </h1>
        <p className="text-muted-foreground mt-5 max-w-4xl text-center text-lg leading-8 text-balance text-shadow-sm">
          输入一批个人资料、笔记或项目上下文，Agent 会围绕来源摄取、证据归档、知识版本、冲突检查、Artifact
          输出和审批流完成长期知识管理，并在确认后把知识转化为可追溯、可更新、可执行的个人知识工作区。
        </p>
        <div className="mt-8 flex items-center justify-center">
          <Button className="size-lg scale-108" size="lg" asChild>
            <a href="https://workspace.knowledge.kotarou.quest">
              <span className="text-md">进入知识工作区</span>
              <ChevronRightIcon className="size-4" />
            </a>
          </Button>
        </div>
      </div>
    </section>
  );
}
