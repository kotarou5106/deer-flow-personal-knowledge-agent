import { cn } from "@/lib/utils";

export function Footer({ className }: { className?: string }) {
  return (
    <footer className={cn("container-md mx-auto mt-32 flex flex-col items-center justify-center", className)}>
      <hr className="from-border/0 to-border/0 m-0 h-px w-full border-none bg-linear-to-r via-white/20" />
      <div className="text-muted-foreground container flex h-20 items-center justify-center text-xs">
        <p>© 2026</p>
      </div>
    </footer>
  );
}
