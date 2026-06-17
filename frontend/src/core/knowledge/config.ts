import { env } from "@/env";

import { getBackendBaseURL } from "../config";
import { isStaticWebsiteOnly } from "../static-mode";

export type KnowledgeFrontendConfig = {
  gatewayBaseUrl: string;
  knowledgeApiBasePath: string;
  demoMode: boolean;
  requestTimeoutMs: number;
  sse: {
    initialRetryMs: number;
    maxRetryMs: number;
    maxRetries: number;
  };
  appEnvironment: "development" | "test" | "production";
};

export type KnowledgeConfigOverrides = Partial<
  Omit<KnowledgeFrontendConfig, "sse">
> & {
  sse?: Partial<KnowledgeFrontendConfig["sse"]>;
};

function parseBoolean(value: string | undefined, fallback: boolean): boolean {
  if (value === undefined) return fallback;
  if (value === "true") return true;
  if (value === "false") return false;
  throw new Error(`Invalid boolean Knowledge config value: ${value}`);
}

function parsePositiveInteger(
  value: string | undefined,
  fallback: number,
  label: string,
): number {
  if (value === undefined) return fallback;
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed <= 0) {
    throw new Error(`${label} must be a positive integer.`);
  }
  return parsed;
}

function normalizeBasePath(value: string): string {
  if (!value.startsWith("/")) {
    throw new Error("Knowledge API base path must start with '/'.");
  }
  return value.replace(/\/+$/, "") || "/api/knowledge";
}

export function resolveKnowledgeFrontendConfig(
  overrides: KnowledgeConfigOverrides = {},
): KnowledgeFrontendConfig {
  const demoMode =
    overrides.demoMode ??
    parseBoolean(
      env.NEXT_PUBLIC_KNOWLEDGE_DEMO_MODE,
      isStaticWebsiteOnly(),
    );
  const gatewayBaseUrl =
    overrides.gatewayBaseUrl ?? getBackendBaseURL().replace(/\/+$/, "");
  const knowledgeApiBasePath = normalizeBasePath(
    overrides.knowledgeApiBasePath ??
      env.NEXT_PUBLIC_KNOWLEDGE_API_BASE_PATH ??
      "/api/knowledge",
  );

  if (!demoMode && gatewayBaseUrl.length > 0) {
    try {
      new URL(gatewayBaseUrl, "http://localhost");
    } catch (error) {
      throw new Error("Gateway base URL is invalid.", { cause: error });
    }
  }

  return {
    gatewayBaseUrl,
    knowledgeApiBasePath,
    demoMode,
    requestTimeoutMs:
      overrides.requestTimeoutMs ??
      parsePositiveInteger(
        env.NEXT_PUBLIC_KNOWLEDGE_REQUEST_TIMEOUT_MS,
        15_000,
        "Knowledge request timeout",
      ),
    sse: {
      initialRetryMs:
        overrides.sse?.initialRetryMs ??
        parsePositiveInteger(
          env.NEXT_PUBLIC_KNOWLEDGE_SSE_INITIAL_RETRY_MS,
          500,
          "Knowledge SSE initial retry",
        ),
      maxRetryMs:
        overrides.sse?.maxRetryMs ??
        parsePositiveInteger(
          env.NEXT_PUBLIC_KNOWLEDGE_SSE_MAX_RETRY_MS,
          5_000,
          "Knowledge SSE max retry",
        ),
      maxRetries:
        overrides.sse?.maxRetries ??
        parsePositiveInteger(
          env.NEXT_PUBLIC_KNOWLEDGE_SSE_MAX_RETRIES,
          6,
          "Knowledge SSE max retries",
        ),
    },
    appEnvironment: overrides.appEnvironment ?? env.NODE_ENV,
  };
}

export function buildKnowledgeUrl(
  config: Pick<
    KnowledgeFrontendConfig,
    "gatewayBaseUrl" | "knowledgeApiBasePath"
  >,
  path: string,
  query?: Record<string, string | number | boolean | null | undefined>,
): string {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  const base = `${config.gatewayBaseUrl}${config.knowledgeApiBasePath}${normalizedPath}`;
  const url = new URL(
    base,
    typeof window !== "undefined" ? window.location.origin : "http://localhost",
  );
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== null) {
      url.searchParams.set(key, String(value));
    }
  }
  return config.gatewayBaseUrl
    ? url.toString()
    : `${url.pathname}${url.search}`;
}
