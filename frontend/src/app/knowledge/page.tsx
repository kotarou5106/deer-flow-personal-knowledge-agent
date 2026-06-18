import {
  ArrowRightIcon,
  CheckCircle2Icon,
  ExternalLinkIcon,
  FileCheck2Icon,
  GitBranchIcon,
  GithubIcon,
  Layers3Icon,
  NetworkIcon,
  ShieldCheckIcon,
  WorkflowIcon,
} from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  knowledgeArchitectureFlow,
  knowledgeArchitectureRuntime,
  knowledgeCapabilities,
  knowledgeDemoSafetyNotice,
  knowledgeDemoStory,
  knowledgeDifferentiators,
  knowledgeLandingHero,
  knowledgeLandingNav,
  knowledgeLifecycleComparison,
  knowledgePublicDemoLinks,
  knowledgeVerificationEvidence,
} from "@/core/knowledge/public-demo";
import { cn } from "@/lib/utils";

export const metadata: Metadata = {
  title: "个人知识智能体 | Personal Knowledge Agent",
  description:
    "一个支持证据追溯、知识版本、冲突检测、持久化工作流、正式产物和审批行动的个人知识智能体。",
  openGraph: {
    title: "个人知识智能体 | Personal Knowledge Agent",
    description:
      "一个支持证据追溯、知识版本、冲突检测、持久化工作流、正式产物和审批行动的个人知识智能体。",
    type: "website",
    url: "/knowledge",
  },
};

const capabilityIcons = [
  FileCheck2Icon,
  ShieldCheckIcon,
  NetworkIcon,
  GitBranchIcon,
  WorkflowIcon,
  CheckCircle2Icon,
];

export default function KnowledgeLandingPage() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-20 border-b bg-background/90 backdrop-blur">
        <nav
          aria-label="Personal Knowledge Agent"
          className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-3 md:px-6"
        >
          <Link href="#overview" className="min-w-0 font-serif text-lg">
            Personal Knowledge Agent
          </Link>
          <div className="hidden items-center gap-1 md:flex">
            {knowledgeLandingNav.map((item) =>
              "external" in item && item.external ? (
                <a
                  key={item.label}
                  href={item.href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="rounded-md px-3 py-2 text-sm text-muted-foreground transition hover:bg-accent hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
                >
                  {item.label}
                </a>
              ) : (
                <Link
                  key={item.label}
                  href={item.href}
                  className="rounded-md px-3 py-2 text-sm text-muted-foreground transition hover:bg-accent hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
                >
                  {item.label}
                </Link>
              ),
            )}
          </div>
          <Button asChild size="sm">
            <Link href={knowledgePublicDemoLinks.demo}>
              {knowledgeLandingHero.primaryCta}
              <ArrowRightIcon aria-hidden="true" />
            </Link>
          </Button>
        </nav>
      </header>

      <main>
        <section
          id="overview"
          className="border-b bg-[linear-gradient(180deg,var(--background)_0%,var(--muted)_100%)]"
        >
          <div className="mx-auto grid max-w-7xl gap-10 px-4 py-16 md:grid-cols-[1fr_0.9fr] md:px-6 md:py-20 lg:py-24">
            <div className="flex flex-col justify-center">
              <Badge variant="outline" className="mb-5 rounded-md">
                {knowledgeLandingHero.badge}
              </Badge>
              <h1 className="max-w-4xl text-4xl leading-tight font-semibold tracking-normal md:text-6xl">
                {knowledgeLandingHero.title}
                <span className="mt-2 block text-3xl text-muted-foreground md:text-5xl">
                  {knowledgeLandingHero.subtitle}
                </span>
              </h1>
              <p className="mt-6 max-w-2xl text-lg leading-8 text-muted-foreground">
                把分散资料转化为可追溯、可更新、可执行的长期知识系统。
              </p>
              <p className="mt-4 max-w-3xl leading-7 text-muted-foreground">
                它不仅回答问题，还追踪知识来源、版本、证据和冲突，生成正式产物，并在审批后把知识转化为受控行动。
              </p>
              <div className="mt-8 flex flex-wrap gap-3">
                <Button asChild size="lg">
                  <Link href={knowledgePublicDemoLinks.demo}>
                    {knowledgeLandingHero.primaryCta}
                    <ArrowRightIcon aria-hidden="true" />
                  </Link>
                </Button>
                <Button asChild variant="outline" size="lg">
                  <Link href={knowledgePublicDemoLinks.architecture}>
                    {knowledgeLandingHero.architectureCta}
                  </Link>
                </Button>
                <Button asChild variant="ghost" size="lg">
                  <a
                    href={knowledgePublicDemoLinks.github}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    <GithubIcon aria-hidden="true" />
                    GitHub
                    <ExternalLinkIcon aria-hidden="true" />
                  </a>
                </Button>
              </div>
            </div>

            <SystemMap />
          </div>
        </section>

        <Section
          id="rag"
          eyebrow="为什么不只是普通 RAG"
          title="从问答链路升级为知识生命周期"
          description="普通 RAG 适合把文档找回来回答一次问题；个人知识智能体关注来源、证据、版本、冲突、产物和审批后的行动。"
        >
          <div className="grid gap-4 lg:grid-cols-2">
            <FlowPanel
              title="普通 RAG"
              items={knowledgeLifecycleComparison.ordinaryRag}
              muted
            />
            <FlowPanel
              title="个人知识智能体"
              items={knowledgeLifecycleComparison.personalKnowledgeAgent}
            />
          </div>
          <div className="mt-6 grid gap-3 md:grid-cols-2 lg:grid-cols-5">
            {knowledgeDifferentiators.map((item) => (
              <article key={item.title} className="rounded-md border bg-card p-4">
                <h3 className="text-sm font-semibold">{item.title}</h3>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">
                  {item.description}
                </p>
              </article>
            ))}
          </div>
        </Section>

        <Section
          id="capabilities"
          eyebrow="核心能力"
          title="核心能力从来源一直延伸到受控行动"
          description="首页只展示能力边界和产品价值；完整交互在 Knowledge Workspace 中查看。"
        >
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {knowledgeCapabilities.map((capability, index) => {
              const Icon = capabilityIcons[index] ?? Layers3Icon;
              return (
                <article
                  key={capability.title}
                  className="rounded-md border bg-card p-5"
                >
                  <Icon className="size-5 text-foreground" aria-hidden="true" />
                  <h3 className="mt-4 text-base font-semibold">
                    {capability.title}
                  </h3>
                  <p className="mt-2 text-sm leading-6 text-muted-foreground">
                    {capability.description}
                  </p>
                  <div className="mt-4 flex flex-wrap gap-2">
                    {capability.keywords.map((keyword) => (
                      <Badge key={keyword} variant="secondary" className="rounded-md">
                        {keyword}
                      </Badge>
                    ))}
                  </div>
                </article>
              );
            })}
          </div>
        </Section>

        <Section
          id="demo-story"
          eyebrow="演示故事"
          title="演示中可以看到什么"
          description="公共 Demo 使用确定性演示数据，完整呈现知识生命周期，不依赖真实外部服务。"
        >
          <ol className="grid gap-3 md:grid-cols-2">
            {knowledgeDemoStory.map((step, index) => (
              <li key={step} className="flex gap-3 rounded-md border bg-card p-4">
                <span className="flex size-7 shrink-0 items-center justify-center rounded-md bg-secondary text-sm font-medium">
                  {index + 1}
                </span>
                <span className="text-sm leading-6 text-muted-foreground">
                  {step}
                </span>
              </li>
            ))}
          </ol>
          <div className="mt-5 rounded-md border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-950 dark:border-amber-900/50 dark:bg-amber-950/20 dark:text-amber-100">
            {knowledgeDemoSafetyNotice}
          </div>
        </Section>

        <Section
          id="architecture"
          eyebrow="系统架构"
          title="公开 Demo 背后的全栈结构"
          description="结构反映现有系统边界：前端入口、Gateway、PostgreSQL / pgvector、持久化知识任务、独立 Worker 和产物存储。"
        >
          <div className="grid gap-4 lg:grid-cols-2">
            <FlowPanel title="运行路径" items={knowledgeArchitectureRuntime} />
            <FlowPanel title="知识链路" items={knowledgeArchitectureFlow} />
          </div>
        </Section>

        <Section
          id="verification"
          eyebrow="验证结果"
          title="真实验证证据，而非流量夸大"
          description="项目定位为生产化导向系统，已经完成真实 Docker Compose 全栈链路验证，但不宣称经过大规模生产流量验证。"
        >
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
            {knowledgeVerificationEvidence.map((item) => (
              <div
                key={item}
                className="flex items-start gap-3 rounded-md border bg-card p-4"
              >
                <CheckCircle2Icon
                  className="mt-0.5 size-4 shrink-0 text-emerald-600"
                  aria-hidden="true"
                />
                <span className="text-sm leading-6">{item}</span>
              </div>
            ))}
          </div>
          <div className="mt-8 flex flex-wrap gap-3">
            <Button asChild size="lg">
              <Link href={knowledgePublicDemoLinks.demo}>
                体验 Demo
                <ArrowRightIcon aria-hidden="true" />
              </Link>
            </Button>
            <Button asChild variant="outline" size="lg">
              <a
                href={knowledgePublicDemoLinks.github}
                target="_blank"
                rel="noopener noreferrer"
              >
                在 GitHub 查看
                <ExternalLinkIcon aria-hidden="true" />
              </a>
            </Button>
          </div>
        </Section>
      </main>
    </div>
  );
}

function Section({
  id,
  eyebrow,
  title,
  description,
  children,
}: {
  id: string;
  eyebrow: string;
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <section id={id} className="border-b">
      <div className="mx-auto max-w-7xl px-4 py-14 md:px-6 md:py-16">
        <div className="mb-8 max-w-3xl">
          <p className="text-sm font-medium text-muted-foreground">{eyebrow}</p>
          <h2 className="mt-3 text-3xl leading-tight font-semibold tracking-normal">
            {title}
          </h2>
          <p className="mt-3 leading-7 text-muted-foreground">{description}</p>
        </div>
        {children}
      </div>
    </section>
  );
}

function FlowPanel({
  title,
  items,
  muted = false,
}: {
  title: string;
  items: readonly string[];
  muted?: boolean;
}) {
  return (
    <article
      className={cn(
        "rounded-md border bg-card p-5",
        muted && "bg-muted/50 text-muted-foreground",
      )}
    >
      <h3 className="font-semibold">{title}</h3>
      <div className="mt-5 flex flex-wrap items-center gap-2">
        {items.map((item, index) => (
          <div key={item} className="flex items-center gap-2">
            <span className="rounded-md border bg-background px-3 py-2 text-sm">
              {item}
            </span>
            {index < items.length - 1 ? (
              <ArrowRightIcon
                className="size-4 text-muted-foreground"
                aria-hidden="true"
              />
            ) : null}
          </div>
        ))}
      </div>
    </article>
  );
}

function SystemMap() {
  const nodes = ["来源", "版本", "证据", "冲突", "工作流", "产物", "审批", "行动"];

  return (
    <div
      aria-label="个人知识智能体生命周期图"
      className="rounded-md border bg-card p-4 shadow-sm md:p-5"
    >
      <div className="flex items-center justify-between border-b pb-4">
        <div>
          <p className="text-sm font-medium">
            {knowledgeLandingHero.lifecycleTitle}
          </p>
          <p className="text-xs text-muted-foreground">
            {knowledgeLandingHero.lifecycleSubtitle}
          </p>
        </div>
        <Badge variant="secondary" className="rounded-md">
          {knowledgeLandingHero.lifecycleBadge}
        </Badge>
      </div>
      <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {nodes.map((node, index) => (
          <div key={node} className="rounded-md border bg-background p-3">
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs text-muted-foreground">
                {String(index + 1).padStart(2, "0")}
              </span>
              {index > 0 ? (
                <span className="h-px min-w-4 flex-1 bg-border" aria-hidden="true" />
              ) : null}
            </div>
            <p className="mt-5 text-sm font-medium">{node}</p>
          </div>
        ))}
      </div>
      <div className="mt-5 rounded-md border bg-muted/50 p-4 text-sm leading-6 text-muted-foreground">
        {knowledgeLandingHero.lifecycleNote}
      </div>
    </div>
  );
}
