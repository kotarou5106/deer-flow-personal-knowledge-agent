"use client";

import { motion } from "motion/react";

import { cn } from "@/lib/utils";

export function Terminal({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
  sequence?: boolean;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 18 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.25 }}
      transition={{ duration: 0.55, ease: "easeOut" }}
      className={cn(
        "z-0 h-full max-h-[400px] w-full max-w-lg overflow-hidden rounded-xl border border-white/10 bg-black shadow-2xl shadow-purple-950/20",
        className,
      )}
      aria-label="工程化部署终端演示"
    >
      <div className="flex h-10 items-center gap-2 border-b border-white/10 bg-zinc-950 px-4" aria-hidden="true">
        <span className="size-2.5 rounded-full bg-red-400/80" />
        <span className="size-2.5 rounded-full bg-amber-400/80" />
        <span className="size-2.5 rounded-full bg-emerald-400/80" />
        <span className="ml-2 font-mono text-[11px] text-zinc-600">knowledge-agent — deployment</span>
      </div>
      <div className="h-[calc(100%-2.5rem)] overflow-auto p-4 font-mono text-sm leading-6">{children}</div>
    </motion.div>
  );
}
