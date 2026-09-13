/** POST-SSE client: fetch + ReadableStream, frame parsing kept pure and testable. */

import { ApiError, fromResponse, toApiError } from "./errors";
import type { ChatStreamRequest } from "./types";

export interface SseEvent {
  event: string;
  data: string;
}

export interface ParseResult {
  events: SseEvent[];
  rest: string;
}

/**
 * Split a buffer into complete SSE frames.
 *
 * Heartbeat comment frames (`: ping`) carry no event name and are dropped here; the
 * trailing partial frame is returned as \`rest\` so callers can prepend the next chunk.
 */
export function parseSseBuffer(buffer: string, options: { final?: boolean } = {}): ParseResult {
  const normalized = buffer.replace(/\r\n/g, "\n");
  const blocks = normalized.split("\n\n");
  const rest = options.final ? "" : (blocks.pop() ?? "");

  const events: SseEvent[] = [];
  for (const block of blocks) {
    const trimmed = block.trim();
    if (!trimmed || trimmed.startsWith(":")) {
      continue; // comment / keep-alive
    }
    let name = "";
    const dataLines: string[] = [];
    for (const line of trimmed.split("\n")) {
      if (line.startsWith("event:")) {
        name = line.slice("event:".length).trim();
      } else if (line.startsWith("data:")) {
        dataLines.push(line.slice("data:".length).trimStart());
      }
    }
    if (name) {
      events.push({ event: name, data: dataLines.join("\n") });
    }
  }
  return { events, rest };
}

export interface ChatStreamHandlers {
  onContent?(text: string): void;
  onReasoning?(text: string): void;
  onMeta?(payload: unknown): void;
  onDone?(payload: { finish_reason?: string | null }): void;
  onError?(error: ApiError): void;
  /** Raw frame hook for diagnostics (dirty frames included). */
  onRawFrame?(event: SseEvent): void;
}

export interface StreamOptions {
  signal?: AbortSignal;
  headers?: Record<string, string>;
  fetchImpl?: typeof fetch;
}

function jsonOrNull(data: string): Record<string, unknown> | null {
  try {
    const parsed: unknown = JSON.parse(data);
    return parsed && typeof parsed === "object" ? (parsed as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

function dispatch(event: SseEvent, handlers: ChatStreamHandlers): void {
  handlers.onRawFrame?.(event);

  if (event.event === "error") {
    const payload = jsonOrNull(event.data);
    handlers.onError?.(
      new ApiError(typeof payload?.message === "string" ? payload.message : "stream error", {
        kind: "server",
        detail: payload,
      }),
    );
    return;
  }

  if (event.event === "done") {
    const payload = jsonOrNull(event.data);
    handlers.onDone?.({ finish_reason: (payload?.finish_reason as string | null) ?? null });
    return;
  }

  const payload = jsonOrNull(event.data);
  if (payload === null) {
    return; // dirty frame: skip, keep the stream alive
  }
  const text = typeof payload.text === "string" ? payload.text : "";

  switch (event.event) {
    case "content":
      handlers.onContent?.(text);
      break;
    case "reasoning":
      handlers.onReasoning?.(text);
      break;
    case "meta":
      handlers.onMeta?.(payload);
      break;
    default:
      break;
  }
}

/**
 * Consume an SSE endpoint. Never throws: transport problems are reported through
 * \`onError\`, and an abort simply stops the callbacks.
 */
export async function streamChat(
  url: string,
  body: ChatStreamRequest,
  handlers: ChatStreamHandlers,
  options: StreamOptions = {},
): Promise<void> {
  const fetchImpl = options.fetchImpl ?? fetch;

  try {
    const response = await fetchImpl(url, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream", ...options.headers },
      body: JSON.stringify(body),
      signal: options.signal,
    });

    if (!response.ok) {
      handlers.onError?.(await fromResponse(response));
      return;
    }
    if (!response.body) {
      handlers.onError?.(new ApiError("stream has no body", { kind: "unknown" }));
      return;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const { events, rest } = parseSseBuffer(buffer);
      buffer = rest;
      for (const event of events) {
        dispatch(event, handlers);
      }
    }

    const { events } = parseSseBuffer(buffer, { final: true });
    for (const event of events) {
      dispatch(event, handlers);
    }
  } catch (error) {
    const apiError = toApiError(error);
    if (apiError.kind === "aborted") {
      return; // user pressed stop: not an error
    }
    handlers.onError?.(apiError);
  }
}
