"use client";

import { Button } from "@/components/ui/button";

import { KnowledgeApiError } from "./errors";

function knowledgeErrorMessage(error: unknown): string {
  if (error instanceof KnowledgeApiError) {
    if (error.kind === "authentication") return "Sign in to use Knowledge.";
    if (error.kind === "authorization") return "Knowledge is not available for this workspace.";
    if (error.kind === "service_unavailable") return "Knowledge is not configured.";
    if (error.kind === "validation") return error.message;
  }
  return "Knowledge is temporarily unavailable.";
}

export function KnowledgeErrorNotice({
  error,
  onRetry,
}: Readonly<{
  error: unknown;
  onRetry?: () => void;
}>) {
  return (
    <div className="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-foreground">
      <div>{knowledgeErrorMessage(error)}</div>
      {process.env.NODE_ENV !== "production" && error instanceof KnowledgeApiError ? (
        <div className="mt-1 text-xs text-muted-foreground">
          {error.kind}
          {error.requestId ? ` / ${error.requestId}` : ""}
        </div>
      ) : null}
      {onRetry ? (
        <Button className="mt-3" size="sm" variant="outline" onClick={onRetry}>
          Retry
        </Button>
      ) : null}
    </div>
  );
}
