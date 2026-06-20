import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function Header({ className }: { className?: string }) {
  return (
    <header className={cn("container-md fixed top-0 right-0 left-0 z-20 mx-auto flex h-16 items-center justify-between px-4 backdrop-blur-xs", className)}>
      <span className="font-serif text-xl">个人知识 Agent</span>
      <nav className="ml-auto flex items-center text-sm font-medium" aria-label="主导航">
        <Button variant="outline" size="sm" asChild className="relative z-10">
          <a href="https://workspace.knowledge.kotarou.quest">进入知识工作区</a>
        </Button>
      </nav>
      <hr className="from-border/0 via-border/70 to-border/0 absolute top-16 right-0 left-0 m-0 h-px w-full border-none bg-linear-to-r" />
    </header>
  );
}
