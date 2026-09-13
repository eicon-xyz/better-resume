/**
 * Transcription WebSocket client (the audioTranscription piece of D05's lib quartet).
 *
 * Responsibilities kept here, and nowhere else:
 * * frames sent while CONNECTING are queued (max 24, like the old audioToTextWs.ts);
 * * identical events are dropped (the wire has no revision, so dedupe is by content key);
 * * a dropped socket reconnects a bounded number of times — old audio is never replayed.
 */

import type { TranscriptEvent } from "./transcriptStore";

export type SocketStatus = "connecting" | "live" | "reconnecting" | "error" | "closed";

export interface TranscriptionSocketOptions {
  url: string;
  ticket: string;
  onEvent: (event: TranscriptEvent) => void;
  onStatus?: (status: SocketStatus, detail?: string | null) => void;
  onDroppedFrames?: (count: number) => void;
  WebSocketImpl?: typeof WebSocket;
  maxQueuedFrames?: number;
  maxReconnects?: number;
  reconnectDelayMs?: number;
  setTimer?: (fn: () => void, ms: number) => unknown;
}

export interface TranscriptionSocket {
  send(frame: Int16Array): void;
  /** Ask the server to freeze the channel and flush its tail (no reconnect). */
  finish(): void;
  stop(): void;
  readonly queuedFrames: number;
  readonly reconnects: number;
}

export const MAX_QUEUED_FRAMES = 24;

export function transcriptionUrl(base: string, ticket: string): string {
  const separator = base.includes("?") ? "&" : "?";
  return `${base}${separator}ticket=${encodeURIComponent(ticket)}`;
}

export function createTranscriptionSocket(options: TranscriptionSocketOptions): TranscriptionSocket {
  const {
    url,
    ticket,
    onEvent,
    onStatus,
    onDroppedFrames,
    WebSocketImpl = WebSocket,
    maxQueuedFrames = MAX_QUEUED_FRAMES,
    maxReconnects = 2,
    reconnectDelayMs = 300,
    setTimer = (fn, ms) => setTimeout(fn, ms),
  } = options;

  let socket: WebSocket | null = null;
  let stopped = false;
  let reconnects = 0;
  let seen = new Set<string>();
  const queue: Int16Array[] = [];

  const eventKey = (event: TranscriptEvent) => `${event.kind}|${event.seg_id ?? ""}|${event.text}`;

  const flush = () => {
    while (queue.length > 0 && socket?.readyState === WebSocketImpl.OPEN) {
      const frame = queue.shift();
      if (frame) socket.send(frame.buffer as ArrayBuffer);
    }
  };

  const connect = () => {
    onStatus?.(reconnects === 0 ? "connecting" : "reconnecting");
    socket = new WebSocketImpl(transcriptionUrl(url, ticket));

    socket.onopen = () => {
      onStatus?.("live");
      flush();
    };

    socket.onmessage = (message: MessageEvent) => {
      if (typeof message.data !== "string") return;
      let parsed: TranscriptEvent;
      try {
        parsed = JSON.parse(message.data) as TranscriptEvent;
      } catch {
        return;
      }
      const key = eventKey(parsed);
      if (seen.has(key)) return;
      seen.add(key);
      onEvent(parsed);
    };

    socket.onclose = () => {
      socket = null;
      if (stopped) {
        onStatus?.("closed");
        return;
      }
      if (reconnects >= maxReconnects) {
        onStatus?.("error", "转写连接已断开");
        return;
      }
      reconnects += 1;
      // Audio is only useful live: drop what was queued for the dead socket.
      if (queue.length > 0) {
        onDroppedFrames?.(queue.length);
        queue.length = 0;
      }
      onStatus?.("reconnecting");
      setTimer(connect, reconnectDelayMs);
    };

    socket.onerror = () => {
      onStatus?.("error", "转写连接出错");
    };
  };

  connect();

  return {
    send(frame: Int16Array) {
      if (stopped) return;
      if (socket?.readyState === WebSocketImpl.OPEN) {
        socket.send(frame.buffer as ArrayBuffer);
        return;
      }
      if (queue.length >= maxQueuedFrames) {
        queue.shift();
        onDroppedFrames?.(1);
      }
      queue.push(frame);
    },
    finish() {
      if (stopped) return;
      stopped = true;
      if (socket?.readyState === WebSocketImpl.OPEN) {
        socket.send(JSON.stringify({ type: "stop" }));
      }
    },

    stop() {
      if (stopped) return;
      stopped = true;
      seen = new Set();
      queue.length = 0;
      socket?.close();
      socket = null;
      onStatus?.("closed");
    },
    get queuedFrames() {
      return queue.length;
    },
    get reconnects() {
      return reconnects;
    },
  };
}
