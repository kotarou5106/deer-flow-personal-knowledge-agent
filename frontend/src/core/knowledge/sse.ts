import { buildKnowledgeUrl, type KnowledgeFrontendConfig } from "./config";
import {
  KnowledgeApiError,
  isNonRetryableKnowledgeError,
  normalizeKnowledgeResponseError,
  normalizeKnowledgeThrownError,
} from "./errors";
import { knowledgeJobEventSchema, type KnowledgeJobEvent } from "./types";

export type KnowledgeJobEventListener = (event: KnowledgeJobEvent) => void;
export type KnowledgeJobEventErrorListener = (error: KnowledgeApiError) => void;

export type KnowledgeJobEventSubscription = {
  close: () => void;
  readonly closed: boolean;
  readonly cursor: number | undefined;
};

export type KnowledgeEventStreamFetch = (
  input: RequestInfo | URL,
  init?: RequestInit,
) => Promise<Response>;

export type SubscribeKnowledgeJobEventsOptions = {
  config: KnowledgeFrontendConfig;
  jobId: string;
  afterSeq?: number;
  signal?: AbortSignal;
  fetchFn?: KnowledgeEventStreamFetch;
  onEvent: KnowledgeJobEventListener;
  onError?: KnowledgeJobEventErrorListener;
  onClose?: () => void;
  retryDelay?: (attempt: number) => number;
};

const terminalEventTypes = new Set([
  "job_succeeded",
  "job_failed",
  "job_cancelled",
]);

const textDecoder = new TextDecoder();

function sleep(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(resolve, ms);
    const abort = () => {
      clearTimeout(timeout);
      reject(new DOMException("Aborted", "AbortError"));
    };
    if (signal.aborted) {
      abort();
      return;
    }
    signal.addEventListener("abort", abort, { once: true });
  });
}

function composeSignals(
  externalSignal: AbortSignal | undefined,
): { signal: AbortSignal; abort: () => void; cleanup: () => void } {
  const controller = new AbortController();
  const abort = () => controller.abort();
  const forwardAbort = () => controller.abort();
  if (externalSignal) {
    if (externalSignal.aborted) {
      controller.abort();
    } else {
      externalSignal.addEventListener("abort", forwardAbort, { once: true });
    }
  }
  return {
    signal: controller.signal,
    abort,
    cleanup: () => externalSignal?.removeEventListener("abort", forwardAbort),
  };
}

function defaultRetryDelay(config: KnowledgeFrontendConfig, attempt: number) {
  const delay = config.sse.initialRetryMs * 2 ** Math.max(0, attempt - 1);
  return Math.min(config.sse.maxRetryMs, delay);
}

export function parseKnowledgeSseChunk(
  chunk: string,
): Array<{ event?: string; data?: string; id?: string }> {
  return chunk
    .split(/\r?\n\r?\n/)
    .filter((frame) => frame.trim().length > 0)
    .flatMap((frame) => {
      const parsed: { event?: string; data?: string; id?: string } = {};
      const data: string[] = [];
      for (const line of frame.split(/\r?\n/)) {
        if (line.startsWith(":")) continue;
        const separator = line.indexOf(":");
        const field = separator === -1 ? line : line.slice(0, separator);
        const rawValue = separator === -1 ? "" : line.slice(separator + 1);
        const value = rawValue.startsWith(" ") ? rawValue.slice(1) : rawValue;
        if (field === "event") parsed.event = value;
        if (field === "id") parsed.id = value;
        if (field === "data") data.push(value);
      }
      if (data.length > 0) parsed.data = data.join("\n");
      return parsed.event || parsed.id || parsed.data ? [parsed] : [];
    });
}

export function subscribeKnowledgeJobEvents({
  config,
  jobId,
  afterSeq,
  signal: externalSignal,
  fetchFn = fetch,
  onEvent,
  onError,
  onClose,
  retryDelay,
}: SubscribeKnowledgeJobEventsOptions): KnowledgeJobEventSubscription {
  const composed = composeSignals(externalSignal);
  let cursor = afterSeq;
  let closed = false;
  let retryAttempt = 0;

  const close = () => {
    if (closed) return;
    closed = true;
    composed.abort();
    composed.cleanup();
    onClose?.();
  };

  async function readStream(response: Response) {
    if (!response.body) {
      throw new KnowledgeApiError({
        kind: "network",
        message: "Knowledge event stream is unavailable.",
      });
    }

    const reader = response.body.getReader();
    let buffer = "";
    while (!closed) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += textDecoder.decode(value, { stream: true });
      const frames = buffer.split(/\r?\n\r?\n/);
      buffer = frames.pop() ?? "";
      for (const frame of frames) {
        for (const parsed of parseKnowledgeSseChunk(frame)) {
          if (!parsed.data) continue;
          const event = knowledgeJobEventSchema.parse(JSON.parse(parsed.data));
          if (cursor !== undefined && event.seq <= cursor) continue;
          cursor = event.seq;
          onEvent(event);
          if (terminalEventTypes.has(parsed.event ?? event.event_type)) {
            close();
            return;
          }
        }
      }
    }
  }

  async function connectLoop() {
    while (!closed) {
      try {
        const response = await fetchFn(
          buildKnowledgeUrl(config, `/jobs/${encodeURIComponent(jobId)}/events`, {
            after_seq: cursor,
          }),
          {
            headers:
              cursor === undefined
                ? { Accept: "text/event-stream" }
                : {
                    Accept: "text/event-stream",
                    "Last-Event-ID": String(cursor),
                  },
            credentials: "include",
            signal: composed.signal,
          },
        );
        if (!response.ok) {
          throw await normalizeKnowledgeResponseError(response);
        }
        retryAttempt = 0;
        await readStream(response);
        if (!closed) {
          retryAttempt += 1;
          if (retryAttempt > config.sse.maxRetries) {
            throw new KnowledgeApiError({
              kind: "network",
              message: "Knowledge event stream retry limit reached.",
            });
          }
          await sleep(
            retryDelay?.(retryAttempt) ?? defaultRetryDelay(config, retryAttempt),
            composed.signal,
          );
        }
      } catch (error) {
        if (closed || composed.signal.aborted) break;
        const normalized = normalizeKnowledgeThrownError(error);
        onError?.(normalized);
        if (
          isNonRetryableKnowledgeError(normalized) ||
          retryAttempt >= config.sse.maxRetries
        ) {
          close();
          break;
        }
        retryAttempt += 1;
        await sleep(
          retryDelay?.(retryAttempt) ?? defaultRetryDelay(config, retryAttempt),
          composed.signal,
        ).catch(() => undefined);
      }
    }
  }

  void connectLoop();

  return {
    close,
    get closed() {
      return closed;
    },
    get cursor() {
      return cursor;
    },
  };
}
