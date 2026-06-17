import { z } from "zod";

export type KnowledgeErrorKind =
  | "network"
  | "timeout"
  | "authentication"
  | "authorization"
  | "csrf"
  | "validation"
  | "not_found"
  | "conflict"
  | "rate_limit"
  | "server"
  | "service_unavailable"
  | "job_failed"
  | "job_cancelled"
  | "unknown";

export type KnowledgeFieldError = {
  path: string[];
  message: string;
};

type KnowledgeErrorInit = {
  kind: KnowledgeErrorKind;
  message: string;
  status?: number;
  code?: string;
  requestId?: string;
  fieldErrors?: KnowledgeFieldError[];
  cause?: unknown;
};

export class KnowledgeApiError extends Error {
  readonly kind: KnowledgeErrorKind;
  readonly status?: number;
  readonly code?: string;
  readonly requestId?: string;
  readonly fieldErrors: KnowledgeFieldError[];

  constructor(init: KnowledgeErrorInit) {
    super(init.message);
    this.name = "KnowledgeApiError";
    this.kind = init.kind;
    this.status = init.status;
    this.code = init.code;
    this.requestId = init.requestId;
    this.fieldErrors = init.fieldErrors ?? [];
    if (init.cause !== undefined) {
      this.cause = init.cause;
    }
  }
}

const structuredErrorSchema = z.object({
  detail: z
    .object({
      error: z.object({
        code: z.string(),
        message: z.string(),
      }),
    })
    .optional(),
  error: z
    .object({
      code: z.string(),
      message: z.string(),
    })
    .optional(),
});

const validationDetailSchema = z.array(
  z.object({
    loc: z.array(z.union([z.string(), z.number()])),
    msg: z.string(),
  }),
);

export function classifyKnowledgeHttpError(
  status: number,
  code?: string,
): KnowledgeErrorKind {
  if (status === 401) return "authentication";
  if (status === 403) return code === "csrf_failed" ? "csrf" : "authorization";
  if (status === 404) return "not_found";
  if (status === 409) return "conflict";
  if (status === 422 || status === 400) return "validation";
  if (status === 429) return "rate_limit";
  if (status === 503 || code === "service_not_configured") {
    return "service_unavailable";
  }
  if (status >= 500) return code === "job_failed" ? "job_failed" : "server";
  return "unknown";
}

function safeMessageForKind(kind: KnowledgeErrorKind, fallback: string): string {
  if (kind === "server" || kind === "unknown") {
    return fallback;
  }
  return fallback;
}

export async function normalizeKnowledgeResponseError(
  response: Response,
): Promise<KnowledgeApiError> {
  const requestId =
    response.headers.get("x-request-id") ??
    response.headers.get("x-correlation-id") ??
    undefined;
  const raw = await response.json().catch(() => undefined);
  const structured = structuredErrorSchema.safeParse(raw);
  const nested = structured.success
    ? (structured.data.detail?.error ?? structured.data.error)
    : undefined;
  const validation = validationDetailSchema.safeParse(
    typeof raw === "object" && raw !== null && "detail" in raw
      ? (raw as { detail?: unknown }).detail
      : undefined,
  );
  const code = nested?.code;
  const kind = classifyKnowledgeHttpError(response.status, code);
  const fallback =
    nested?.message ??
    (response.statusText || "Knowledge request failed");

  return new KnowledgeApiError({
    kind,
    status: response.status,
    code,
    requestId,
    message: safeMessageForKind(kind, fallback),
    fieldErrors: validation.success
      ? validation.data.map((item) => ({
          path: item.loc.map(String),
          message: item.msg,
        }))
      : [],
  });
}

export function normalizeKnowledgeThrownError(error: unknown): KnowledgeApiError {
  if (error instanceof KnowledgeApiError) return error;
  if (error instanceof DOMException && error.name === "AbortError") {
    return new KnowledgeApiError({
      kind: "timeout",
      message: "Knowledge request timed out or was aborted.",
      cause: error,
    });
  }
  if (error instanceof Error) {
    return new KnowledgeApiError({
      kind: "network",
      message: "Knowledge service is unreachable.",
      cause: error,
    });
  }
  return new KnowledgeApiError({
    kind: "unknown",
    message: "Knowledge request failed.",
    cause: error,
  });
}

export function isNonRetryableKnowledgeError(error: unknown): boolean {
  if (!(error instanceof KnowledgeApiError)) return false;
  return ["authentication", "authorization", "csrf", "not_found"].includes(
    error.kind,
  );
}
