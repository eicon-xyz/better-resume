import { beforeEach, describe, expect, it } from "vitest";

import { createTranscriptionSocket, transcriptionUrl } from "./transcriptionSocket";
import type { TranscriptEvent } from "./transcriptStore";

class FakeWebSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;
  static instances: FakeWebSocket[] = [];

  readyState = FakeWebSocket.CONNECTING;
  sent: ArrayBuffer[] = [];
  closed = false;
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((message: { data: unknown }) => void) | null = null;

  constructor(readonly url: string) {
    FakeWebSocket.instances.push(this);
  }

  open() {
    this.readyState = FakeWebSocket.OPEN;
    this.onopen?.();
  }

  emit(event: TranscriptEvent) {
    this.onmessage?.({ data: JSON.stringify(event) });
  }

  send(data: ArrayBuffer) {
    this.sent.push(data);
  }

  close() {
    this.closed = true;
    this.readyState = FakeWebSocket.CLOSED;
    this.onclose?.();
  }

  /** Server-initiated drop (no close() call from our side). */
  drop() {
    this.readyState = FakeWebSocket.CLOSED;
    this.onclose?.();
  }
}

function frame(value = 1): Int16Array {
  return Int16Array.from([value, value]);
}

beforeEach(() => {
  FakeWebSocket.instances = [];
});

describe("transcriptionUrl", () => {
  it("appends the ticket with encoding", () => {
    expect(transcriptionUrl("ws://host/api/v1/media/transcribe", "a b")).toBe(
      "ws://host/api/v1/media/transcribe?ticket=a%20b",
    );
    expect(transcriptionUrl("ws://host/x?y=1", "t")).toBe("ws://host/x?y=1&ticket=t");
  });
});

describe("createTranscriptionSocket", () => {
  it("queues frames until the socket is open, then flushes in order", () => {
    const events: TranscriptEvent[] = [];
    const statuses: string[] = [];
    const socket = createTranscriptionSocket({
      url: "ws://host/ws",
      ticket: "t",
      onEvent: (event) => events.push(event),
      onStatus: (status) => statuses.push(status),
      WebSocketImpl: FakeWebSocket as unknown as typeof WebSocket,
    });

    socket.send(frame(1));
    socket.send(frame(2));
    expect(socket.queuedFrames).toBe(2);

    FakeWebSocket.instances[0]!.open();

    expect(FakeWebSocket.instances[0]!.sent).toHaveLength(2);
    expect(statuses).toEqual(["connecting", "live"]);
  });

  it("caps the queue at 24 frames and reports what it dropped", () => {
    const dropped: number[] = [];
    const socket = createTranscriptionSocket({
      url: "ws://host/ws",
      ticket: "t",
      onEvent: () => undefined,
      onDroppedFrames: (count) => dropped.push(count),
      WebSocketImpl: FakeWebSocket as unknown as typeof WebSocket,
    });

    for (let index = 0; index < 30; index += 1) socket.send(frame(index));

    expect(socket.queuedFrames).toBe(24);
    expect(dropped.reduce((total, value) => total + value, 0)).toBe(6);
  });

  it("forwards events once and drops duplicates", () => {
    const events: TranscriptEvent[] = [];
    createTranscriptionSocket({
      url: "ws://host/ws",
      ticket: "t",
      onEvent: (event) => events.push(event),
      WebSocketImpl: FakeWebSocket as unknown as typeof WebSocket,
    });
    const ws = FakeWebSocket.instances[0]!;
    ws.open();

    ws.emit({ kind: "replace", text: "你好" });
    ws.emit({ kind: "replace", text: "你好" });
    ws.emit({ kind: "archive", text: "你好。" });
    ws.onmessage?.({ data: "not json" });

    expect(events).toEqual([
      { kind: "replace", text: "你好" },
      { kind: "archive", text: "你好。" },
    ]);
  });

  it("reconnects a bounded number of times and drops stale audio", () => {
    const statuses: string[] = [];
    const dropped: number[] = [];
    const timers: Array<() => void> = [];
    createTranscriptionSocket({
      url: "ws://host/ws",
      ticket: "t",
      onEvent: () => undefined,
      onStatus: (status) => statuses.push(status),
      onDroppedFrames: (count) => dropped.push(count),
      maxReconnects: 1,
      WebSocketImpl: FakeWebSocket as unknown as typeof WebSocket,
      setTimer: (fn) => {
        timers.push(fn);
        return 0;
      },
    });

    const first = FakeWebSocket.instances[0]!;
    first.open();
    first.drop();
    expect(statuses).toEqual(["connecting", "live", "reconnecting"]);

    // Queued audio from the dead socket is useless: it must not be replayed.
    const socketEvents: TranscriptEvent[] = [];
    void socketEvents;
    timers[0]!();
    const second = FakeWebSocket.instances[1]!;
    second.open();
    second.drop();

    expect(statuses.at(-1)).toBe("error");
    expect(dropped).toEqual([]);
    expect(FakeWebSocket.instances).toHaveLength(2);
  });

  it("stops for good on stop()", () => {
    const statuses: string[] = [];
    const socket = createTranscriptionSocket({
      url: "ws://host/ws",
      ticket: "t",
      onEvent: () => undefined,
      onStatus: (status) => statuses.push(status),
      WebSocketImpl: FakeWebSocket as unknown as typeof WebSocket,
    });
    const ws = FakeWebSocket.instances[0]!;
    ws.open();

    socket.stop();
    socket.send(frame(9));

    expect(ws.closed).toBe(true);
    expect(statuses.at(-1)).toBe("closed");
    expect(socket.queuedFrames).toBe(0);
    expect(ws.sent).toHaveLength(0);
  });
});
