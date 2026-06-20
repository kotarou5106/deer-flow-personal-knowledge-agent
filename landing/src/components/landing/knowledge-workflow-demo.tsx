"use client";

import { AnimatePresence, motion } from "motion/react";
import { Check, FileText, Folder, Pause, Play, RotateCcw, Sparkles } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { cn } from "@/lib/utils";
import { workflowArtifacts, workflowStages } from "./knowledge-workflow-model";

const STEP_DURATION = 1150;

export function KnowledgeWorkflowDemo() {
  const [activeStep, setActiveStep] = useState(-1);
  const [isPlaying, setIsPlaying] = useState(false);
  const [hasStarted, setHasStarted] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const start = useCallback(() => {
    setActiveStep(0);
    setHasStarted(true);
    setIsPlaying(true);
  }, []);

  useEffect(() => {
    if (!isPlaying) return;
    if (activeStep >= workflowStages.length) return;
    const timer = window.setTimeout(() => {
      const nextStep = activeStep + 1;
      setActiveStep(nextStep);
      if (nextStep >= workflowStages.length) setIsPlaying(false);
    }, STEP_DURATION);
    return () => window.clearTimeout(timer);
  }, [activeStep, isPlaying]);

  useEffect(() => {
    const element = containerRef.current;
    if (!element || hasStarted) return;
    const observer = new IntersectionObserver(([entry]) => {
      if (entry?.isIntersecting) {
        start();
        observer.disconnect();
      }
    }, { threshold: 0.35 });
    observer.observe(element);
    return () => observer.disconnect();
  }, [hasStarted, start]);

  const complete = activeStep >= workflowStages.length;

  return (
    <div ref={containerRef} className="container-md mx-auto px-4 md:px-8">
      <div className="overflow-hidden rounded-2xl border border-white/10 bg-zinc-950/80 shadow-2xl shadow-sky-950/20">
        <div className="flex flex-wrap items-center gap-3 border-b border-white/10 px-4 py-3 md:px-6">
          <div className="flex gap-1.5" aria-hidden="true"><span className="size-2.5 rounded-full bg-red-400/70" /><span className="size-2.5 rounded-full bg-amber-400/70" /><span className="size-2.5 rounded-full bg-emerald-400/70" /></div>
          <span className="font-mono text-xs text-zinc-500">knowledge-agent / workflow</span>
          <div className="ml-auto flex items-center gap-2">
            <button type="button" onClick={() => complete ? start() : setIsPlaying((playing) => !playing)} className="inline-flex h-8 items-center gap-2 rounded-md border border-white/10 bg-white/5 px-3 text-xs font-medium text-zinc-200 transition hover:border-sky-400/40 hover:bg-sky-400/10 focus-visible:ring-2 focus-visible:ring-sky-400 focus-visible:outline-none" aria-label={complete ? "重播工作流" : isPlaying ? "暂停工作流" : "播放工作流"}>
              {complete ? <RotateCcw className="size-3.5" /> : isPlaying ? <Pause className="size-3.5" /> : <Play className="size-3.5" />}
              {complete ? "重播" : isPlaying ? "暂停" : "播放"}
            </button>
          </div>
        </div>

        <div className="grid min-h-[520px] lg:grid-cols-[0.9fr_1.1fr]">
          <div className="border-b border-white/10 p-5 lg:border-r lg:border-b-0 md:p-7">
            <div className="mb-5 flex items-center gap-2 font-mono text-xs text-zinc-500"><Folder className="size-4" /> personal-knowledge/</div>
            <div className="space-y-2">
              {workflowStages.map((stage, index) => {
                const done = activeStep > index;
                const active = activeStep === index;
                return (
                  <motion.div key={stage.file} animate={{ x: active ? 8 : 0 }} className={cn("flex items-center gap-3 rounded-md border px-3 py-2.5 font-mono text-sm transition-colors", done && "border-emerald-500/20 bg-emerald-500/5 text-emerald-300", active && "border-sky-400/30 bg-sky-400/10 text-sky-200", !done && !active && "border-transparent text-zinc-600")}>
                    <FileText className="size-4 shrink-0" />
                    <span className="truncate">{stage.file}</span>
                    {done && <Check className="ml-auto size-4" />}
                    {active && <Sparkles className="ml-auto size-4 animate-pulse" />}
                  </motion.div>
                );
              })}
            </div>
          </div>

          <div className="flex min-h-[480px] flex-col p-5 md:p-7" aria-live="polite">
            <div className="mb-5 flex items-center gap-2"><span className="size-2.5 rounded-full bg-emerald-400" /><span className="text-sm text-zinc-400">个人知识 Agent</span><span className="ml-auto font-mono text-[11px] text-zinc-600">浏览器端静态演示</span></div>
            <div className="mb-5 flex justify-end"><div className="max-w-[88%] rounded-2xl rounded-tr-sm bg-sky-600 px-4 py-3 text-sm text-white">整理项目部署记录，保留证据、冲突和后续行动。</div></div>
            <div className="flex-1 space-y-3">
              <AnimatePresence initial={false}>
                {workflowStages.slice(0, Math.min(activeStep + 1, workflowStages.length)).map((stage, index) => (
                  <motion.div key={stage.title} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="rounded-lg border border-white/8 bg-white/[0.025] px-4 py-3">
                    <div className="flex items-center gap-3"><span className={cn("flex size-6 items-center justify-center rounded-full border font-mono text-[10px]", activeStep > index ? "border-emerald-400/30 text-emerald-300" : "border-sky-400/30 text-sky-300")}>{activeStep > index ? <Check className="size-3.5" /> : index + 1}</span><span className="text-sm font-medium text-zinc-200">{stage.title}</span></div>
                    <p className="mt-2 pl-9 text-sm text-zinc-500">{stage.detail}</p>
                  </motion.div>
                ))}
              </AnimatePresence>
            </div>
            {complete && (
              <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="mt-5 rounded-lg border border-emerald-400/20 bg-emerald-400/5 p-4">
                <div className="mb-3 flex items-center gap-2 text-sm font-medium text-emerald-300"><Check className="size-4" /> 工作流完成，等待受控行动</div>
                <div className="flex flex-wrap gap-2">{workflowArtifacts.map((artifact) => <span key={artifact} className="rounded-md border border-white/8 bg-black/20 px-3 py-2 font-mono text-xs text-zinc-300">{artifact}</span>)}</div>
              </motion.div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
