"use client";

import { Terminal } from "@/components/ui/terminal";
import { Section } from "../section";

const terminalLines = [
  ["$ docker compose up -d postgres gateway knowledge-worker frontend nginx", "text-zinc-100"],
  ["✓ postgres healthy", "text-emerald-400"],
  ["✓ pgvector extension ready", "text-emerald-400"],
  ["✓ knowledge-worker started", "text-emerald-400"],
  ["✓ gateway started", "text-emerald-400"],
  ["✓ frontend started", "text-emerald-400"],
  ["✓ nginx started", "text-emerald-400"],
  ["$ knowledge-agent status --verbose", "mt-3 text-zinc-100"],
  ["storage        PostgreSQL / pgvector", "text-zinc-400"],
  ["ingestion      ready", "text-zinc-400"],
  ["artifact       ready", "text-zinc-400"],
  ["approval-flow  enforced", "text-zinc-400"],
  ["workspace      workspace.knowledge.kotarou.quest", "text-sky-300"],
] as const;

export function SandboxSection() {
  return (
    <Section title="工程化部署" subtitle="PostgreSQL / pgvector / Gateway / Worker / nginx / HTTPS / ECS / Docker Compose">
      <div className="container-md mx-auto mt-8 flex w-full flex-col items-center gap-12 px-4 lg:flex-row lg:gap-16 md:px-8">
        <div className="w-full flex-1">
          <Terminal className="h-[400px] w-full" sequence={false}>
            <div className="grid gap-y-1 text-sm font-normal tracking-tight">
              {terminalLines.map(([line, className]) => <span key={line} className={className}>{line}</span>)}
            </div>
          </Terminal>
        </div>
        <div className="w-full flex-1 space-y-6">
          <div className="space-y-4"><p className="text-sm font-medium tracking-wider text-purple-400 uppercase">Production Delivery</p><h3 className="text-4xl font-bold tracking-tight lg:text-5xl">Docker + PostgreSQL + nginx + HTTPS</h3></div>
          <p className="text-lg leading-8 text-zinc-400">Docker Compose 编排完整服务，PostgreSQL 与 pgvector 持久化知识，Gateway 和 Worker 处理任务，nginx 通过 HTTPS 提供工作区入口。</p>
          <div className="flex flex-wrap gap-3 pt-4">{["Docker Compose", "PostgreSQL", "pgvector", "Worker", "Gateway", "nginx", "HTTPS", "ECS"].map((tag) => <span key={tag} className="rounded-full border border-zinc-800 bg-zinc-900 px-4 py-2 text-sm text-zinc-300">{tag}</span>)}</div>
        </div>
      </div>
    </Section>
  );
}
