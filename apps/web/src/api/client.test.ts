import { describe, expect, it, vi } from "vitest";

import { createApiClient } from "./client";
import { ApiError } from "./errors";

function jsonResponse(payload: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { "content-type": "application/json" },
    ...init,
  });
}

describe("createApiClient", () => {
  it("posts JSON with cookie credentials and returns the typed session", async () => {
    const session = {
      id: "s1",
      kind: "chat",
      title: "会话",
      model_ref: null,
      message_count: 0,
      created_at: "2026-09-13T00:00:00Z",
      updated_at: "2026-09-13T00:00:00Z",
    };
    const fetchImpl = vi.fn(() => jsonResponse(session));
    const client = createApiClient({ fetchImpl: fetchImpl as unknown as typeof fetch });

    const created = await client.createChatSession({ title: "会话" });

    expect(created.id).toBe("s1");
    expect(fetchImpl).toHaveBeenCalledWith(
      "/api/v1/chat/sessions",
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: "会话" }),
      }),
    );
  });

  it("sends query parameters for history paging", async () => {
    let requestedUrl = "";
    const fetchImpl = (url: string) => {
      requestedUrl = url;
      return jsonResponse([]);
    };
    const client = createApiClient({ fetchImpl: fetchImpl as unknown as typeof fetch });

    await client.listChatMessages("s1", { before: 7, limit: 20 });

    expect(requestedUrl).toBe("/api/v1/chat/sessions/s1/messages?before=7&limit=20");
  });

  it("resolves undefined for 204 responses", async () => {
    const fetchImpl = () => new Response(null, { status: 204 });
    const client = createApiClient({ fetchImpl: fetchImpl as unknown as typeof fetch });

    await expect(client.deleteChatSession("s1")).resolves.toBeUndefined();
  });

  it("normalizes HTTP errors and reports them once", async () => {
    const onError = vi.fn();
    const fetchImpl = () =>
      new Response(JSON.stringify({ detail: "conversation not found" }), { status: 404 });
    const client = createApiClient({
      fetchImpl: fetchImpl as unknown as typeof fetch,
      onError,
    });

    await expect(client.listChatSessions()).rejects.toBeInstanceOf(ApiError);
    expect(onError).toHaveBeenCalledTimes(1);
    expect(onError.mock.calls[0]?.[0]).toMatchObject({ kind: "not_found", status: 404 });
  });

  it("surfaces unauthorized separately", async () => {
    const fetchImpl = () => new Response(null, { status: 401 });
    const client = createApiClient({ fetchImpl: fetchImpl as unknown as typeof fetch });

    await expect(client.currentPrincipal()).rejects.toMatchObject({ kind: "unauthorized" });
  });

  it("times out slow requests without confusing them with aborts", async () => {
    const fetchImpl = (_url: string, init?: RequestInit) =>
      new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener("abort", () => {
          // AbortSignal reasons are DOMExceptions on purpose (name carries the cause).
          // eslint-disable-next-line @typescript-eslint/prefer-promise-reject-errors
          reject(init.signal?.reason);
        });
      });
    const client = createApiClient({ fetchImpl: fetchImpl as unknown as typeof fetch, timeoutMs: 10 });

    await expect(client.listModels()).rejects.toMatchObject({ kind: "timeout" });
  });

  it("keeps caller aborts distinct from timeouts", async () => {
    const controller = new AbortController();
    const fetchImpl = (_url: string, init?: RequestInit) =>
      new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener("abort", () => {
          // eslint-disable-next-line @typescript-eslint/prefer-promise-reject-errors
          reject(init.signal?.reason);
        });
      });
    const client = createApiClient({ fetchImpl: fetchImpl as unknown as typeof fetch });

    const pending = client
      .listModels({ signal: controller.signal })
      .catch((error: ApiError) => error);
    controller.abort();

    await expect(pending).resolves.toMatchObject({ kind: "aborted" });
  });

  it("delegates streaming to the SSE client with typed handlers", async () => {
    const encoder = new TextEncoder();
    const fetchImpl = () =>
      new Response(
        new ReadableStream<Uint8Array>({
          start(controller) {
            controller.enqueue(encoder.encode('event: content\ndata: {"text":"你"}\n\n'));
            controller.enqueue(encoder.encode('event: done\ndata: {"finish_reason":"stop"}\n\n'));
            controller.close();
          },
        }),
        { status: 200 },
      );
    const client = createApiClient({ fetchImpl: fetchImpl as unknown as typeof fetch });
    const seen: string[] = [];

    await client.streamChat(
      "s1",
      { content: "你好", client_message_id: "cm-1" },
      {
        onContent: (text) => seen.push(text),
        onDone: () => seen.push("done"),
      },
    );

    expect(seen).toEqual(["你", "done"]);
  });
});
