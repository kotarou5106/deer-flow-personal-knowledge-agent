import { cn } from "@/lib/utils";

export function Section({ className, title, subtitle, children }: { className?: string; title: React.ReactNode; subtitle?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className={cn("mx-auto flex w-full flex-col py-16", className)}>
      <header className="flex flex-col items-center justify-between px-4">
        <h2 className="mb-4 bg-linear-to-r from-white via-gray-200 to-gray-400 bg-clip-text text-center text-4xl font-bold text-transparent md:text-5xl">{title}</h2>
        {subtitle && <div className="text-muted-foreground max-w-5xl text-center text-lg md:text-xl">{subtitle}</div>}
      </header>
      <div className="mt-4">{children}</div>
    </section>
  );
}
