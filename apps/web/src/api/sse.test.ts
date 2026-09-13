import { describe, expect, it, vi } from "vitest";

import { parseSseBuffer, streamChat } from "./sse";

function streamResponse(chunks: string[]): Response {
  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(encoder.encode(chunk));
      }
      controller.close();
    },
  });
  return new Response(stream, {
    status: 200,
    headers: { "content-type": "text/event-stream" },
  });
}

describe("parseSseBuffer", () => {
  it("parses complete frames and keeps the partial tail", () => {
    const { events, rest } = parseSseBuffer('event: content\ndata: {"text":"a"}\n\nevent: reaso');

    expect(events).toEqual([{ event: "content", data: '{"text":"a"}' }]);
    expect(rest).toBe("event: reaso");
  });

  it("drops heartbeat comments and multi-line data is joined", () => {
    const { events } = parseSseBuffer(
      ": ping\n\nevent: content\ndata: line1\ndata: line2\n\n",
      { final: true },
    );

    expect(events).toEqual([{ event: "content", data: "line1\nline2" }]);
  });

  it("does not emit frames without an event name", () => {
    const { events } = parseSseBuffer("data: orphan\n\n", { final: true });

    expect(events).toEqual([]);
  });
});

describe("streamChat", () => {
  it("dispatches content, reasoning, meta and done in order", async () => {
    const calls: string[] = [];
    const fetchImpl = vi.fn(() =>
      streamResponse([
        'event: reasoning\ndata: {"text":"先想"}\n\n',
        'event: content\ndata: {"text":"你"}\n\n',
        'event: content\ndata: {"text":"好"}\n\n',
        'event: meta\ndata: {"model":"deepseek-flash"}\n\n: ping\n\n',
        'event: done\ndata: {"finish_reason":"stop"}\n\n',
      ]),
    );

    await streamChat(
      "/api/v1/chat/sessions/s1/stream",
      { content: "你好" },
      {
        onContent: (text) => calls.push(`content:${text}`),
        onReasoning: (text) => calls.push(`reasoning:${text}`),
        onMeta: () => calls.push("meta"),
        onDone: (payload) => calls.push(`done:${payload.finish_reason ?? ""}`),
      },
      { fetchImpl: fetchImpl as unknown as typeof fetch },
    );

    expect(calls).toEqual(["reasoning:先想", "content:你", "content:好", "meta", "done:stop"]);
    expect(fetchImpl).toHaveBeenCalledWith(
      "/api/v1/chat/sessions/s1/stream",
      expect.objectContaining({ method: "POST", credentials: "include" }),
    );
  });

  it("skips dirty frames without losing the stream", async () => {
    const content: string[] = [];
    const fetchImpl = () =>
      streamResponse([
        "event: content\ndata: {oops\n\n",
        'event: content\ndata: {"text":"ok"}\n\n',
        'event: done\ndata: {}\n\n',
      ]);

    await streamChat(
      "/stream",
      { content: "hi" },
      { onContent: (text) => content.push(text) },
      { fetchImpl: fetchImpl as unknown as typeof fetch },
    );

    expect(content).toEqual(["ok"]);
  });

  it("reports an error frame through onError", async () => {
    const onError = vi.fn();
    const fetchImpl = () =>
      streamResponse(['event: error\ndata: {"message":"upstream down","kind":"retryable"}\n\n']);

    await streamChat(
      "/stream",
      { content: "hi" },
      { onError },
      { fetchImpl: fetchImpl as unknown as typeof fetch },
    );

    expect(onError).toHaveBeenCalledTimes(1);
    expect(onError.mock.calls[0]?.[0]).toMatchObject({ message: "upstream down" });
  });

  it("stops calling handlers once aborted", async () => {
    const controller = new AbortController();
    const content: string[] = [];
    const onDone = vi.fn();

    const encoder = new TextEncoder();
    const fetchImpl = () =>
      new Response(
        new ReadableStream<Uint8Array>({
          start(streamController) {
            streamController.enqueue(encoder.encode('event: content\ndata: {"text":"第一帧"}\n\n'));
          },
          pull() {
            controller.abort();
            return Promise.reject(new DOMException("aborted", "AbortError"));
          },
        }),
        { status: 200 },
      );

    await streamChat(
      "/stream",
      { content: "hi" },
      { onContent: (text) => content.push(text), onDone },
      { fetchImpl: fetchImpl as unknown as typeof fetch, signal: controller.signal },
    );

    expect(content).toEqual(["第一帧"]);
    expect(onDone).not.toHaveBeenCalled();
  });

  it("maps a non-ok response into onError", async () => {
    const onError = vi.fn();
    const fetchImpl = () =>
      new Response(JSON.stringify({ detail: "no model configured" }), { status: 503 });

    await streamChat("/stream", { content: "hi" }, { onError }, { fetchImpl: fetchImpl as unknown as typeof fetch });

    expect(onError.mock.calls[0]?.[0]).toMatchObject({ kind: "server", status: 503 });
  });
});
