import { isStateChangingMethod, readCsrfCookie } from "@/core/api/fetcher";

import { buildKnowledgeUrl, type KnowledgeFrontendConfig } from "./config";
import {
  normalizeKnowledgeResponseError,
  normalizeKnowledgeThrownError,
} from "./errors";
import type {
  KnowledgeTransport,
  KnowledgeTransportRequest,
} from "./types";

export type FetchLike = (
  input: RequestInfo | URL,
  init?: RequestInit,
) => Promise<Response>;

function composeAbortSignal(
  externalSignal: AbortSignal | undefined,
  timeoutMs: number,
): { signal: AbortSignal; cleanup: () => void } {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  const abort = () => controller.abort();
  if (externalSignal) {
    if (externalSignal.aborted) {
      controller.abort();
    } else {
      externalSignal.addEventListener("abort", abort, { once: true });
    }
  }
  return {
    signal: controller.signal,
    cleanup: () => {
      clearTimeout(timeout);
      externalSignal?.removeEventListener("abort", abort);
    },
  };
}

function jsonHeaders(method: string, body: unknown): Headers {
  const headers = new Headers({ Accept: "application/json" });
  if (body !== undefined) {
    headers.set("Content-Type", "application/json");
  }
  if (isStateChangingMethod(method)) {
    const csrf = readCsrfCookie();
    if (csrf) {
      headers.set("X-CSRF-Token", csrf);
    }
  }
  return headers;
}

export class GatewayKnowledgeTransport implements KnowledgeTransport {
  private readonly config: KnowledgeFrontendConfig;
  private readonly fetchFn: FetchLike;

  constructor(
    config: KnowledgeFrontendConfig,
    fetchFn: FetchLike = globalThis.fetch.bind(globalThis),
  ) {
    this.config = config;
    this.fetchFn = fetchFn;
  }

  async request(request: KnowledgeTransportRequest): Promise<unknown> {
    const { signal, cleanup } = composeAbortSignal(
      request.signal,
      request.timeoutMs ?? this.config.requestTimeoutMs,
    );
    try {
      const response = await this.fetchFn(
        buildKnowledgeUrl(this.config, request.path, request.query),
        {
          method: request.method,
          headers: jsonHeaders(request.method, request.body),
          body:
            request.body === undefined
              ? undefined
              : JSON.stringify(request.body),
          credentials: "include",
          signal,
        },
      );
      if (!response.ok) {
        throw await normalizeKnowledgeResponseError(response);
      }
      if (response.status === 204) {
        return {};
      }
      return await response.json();
    } catch (error) {
      throw normalizeKnowledgeThrownError(error);
    } finally {
      cleanup();
    }
  }
}
