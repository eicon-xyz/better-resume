import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ApiClient } from "../api/client";
import { ApiError } from "../api/errors";
import type { ChatSessionView, ChatStreamRequest } from "../api/types";
import type { ChatStreamHandlers } from "../api/sse";
import { useChatStore } from "./store";
import { useChatStream } from "./useChatStream";

const SESSION: ChatSessionView = {
  id: "s-new",
  kind: "chat",
  title: "新会话",
  model_ref: null,
  message_count: 0,
  created_at: "2026-09-13T00:00:00Z",
  updated_at: "2026-09-13T00:00:00Z",
};

interface FakeClient {
  client: ApiClient;
  order: string[];
  streams: Array<{
    sessionId: string;
    body: ChatStreamRequest;
    handlers: ChatStreamHandlers;
    signal?: AbortSignal;
  }>;
}

function fakeClient(): FakeClient {
  const order: string[] = [];
  const streams: FakeClient["streams"] = [];

  const client = {
    createChatSession: vi.fn(() => {
      order.push("create");
      return Promise.resolve(SESSION);
    }),
    streamChat: vi.fn(
      (
        sessionId: string,
        body: ChatStreamRequest,
        handlers: ChatStreamHandlers,
        options?: { signal?: AbortSignal },
      ) => {
        order.push("stream");
        streams.push({ sessionId, body, handlers, signal: options?.signal });
        return Promise.resolve();
      },
    ),
    listChatSessions: vi.fn(() => Promise.resolve([])),
    listChatMessages: vi.fn(() => Promise.resolve([])),
    listModels: vi.fn(() => Promise.resolve([])),
  } as unknown as ApiClient;

  return { client, order, streams };
}

function wrapper(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

function renderChat(client: ApiClient, sessionId: string | null, onSessionCreated?: (id: string) => void) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return renderHook(() => useChatStream({ client, sessionId, onSessionCreated }), {
    wrapper: wrapper(queryClient),
  });
}

async function flushTypewriter(ms = 200): Promise<void> {
  await act(() => {
    vi.advanceTimersByTime(ms);
    return Promise.resolve();
  });
}

describe("useChatStream", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    useChatStore.getState().reset();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("creates the session before streaming and follows with navigation", async () => {
    const { client, order, streams } = fakeClient();
    const created: string[] = [];
    const { result } = renderChat(client, null, (id) => created.push(id));

    await act(async () => {
      await result.current.send("你好");
    });

    expect(order).toEqual(["create", "stream"]);
    expect(created).toEqual(["s-new"]);
    expect(streams[0]?.sessionId).toBe("s-new");
    expect(streams[0]?.body.client_message_id).toBeTruthy();
  });

  it("renders streamed content and reasoning through the typewriter", async () => {
    const { client, streams } = fakeClient();
    const { result } = renderChat(client, "s-1");

    await act(async () => {
      await result.current.send("你好");
    });
    act(() => {
      streams[0]?.handlers.onReasoning?.("先想一下");
      streams[0]?.handlers.onContent?.("你");
      streams[0]?.handlers.onContent?.("好");
      streams[0]?.handlers.onDone?.({ finish_reason: "stop" });
    });
    await flushTypewriter();

    const messages = useChatStore.getState().messages;
    expect(messages).toHaveLength(2);
    expect(messages[0]).toMatchObject({ role: "user", content: "你好" });
    expect(messages[1]).toMatchObject({ role: "assistant", content: "你好", reasoning: "先想一下" });
  });

  it("keeps a reasoning-only first frame from blanking the message", async () => {
    const { client, streams } = fakeClient();
    const { result } = renderChat(client, "s-1");

    await act(async () => {
      await result.current.send("为什么");
    });
    act(() => {
      streams[0]?.handlers.onReasoning?.("只有思考");
    });
    await flushTypewriter();

    const assistant = useChatStore.getState().messages[1];
    expect(assistant).toMatchObject({ content: "", reasoning: "只有思考", streaming: true });
  });

  it("drops late chunks once another session is opened", async () => {
    const { client, streams } = fakeClient();
    const { result } = renderChat(client, "s-1");

    await act(async () => {
      await result.current.send("第一问");
    });
    act(() => {
      streams[0]?.handlers.onContent?.("第一帧");
    });
    await flushTypewriter();

    act(() => {
      useChatStore.getState().openSession("s-2"); // user switched conversation
    });
    act(() => {
      streams[0]?.handlers.onContent?.("过期内容");
    });
    await flushTypewriter();

    expect(useChatStore.getState().messages).toEqual([]);
  });

  it("surfaces stream errors on the store", async () => {
    const { client, streams } = fakeClient();
    const { result } = renderChat(client, "s-1");

    await act(async () => {
      await result.current.send("会失败");
    });
    act(() => {
      streams[0]?.handlers.onError?.(new ApiError("上游超时", { kind: "timeout" }));
    });

    expect(result.current.error).toBe("上游超时");
    expect(useChatStore.getState().messages[1]).toMatchObject({ error: "上游超时", streaming: false });
  });

  it("reports session creation failures without streaming", async () => {
    const { client, order } = fakeClient();
    const failing = (): never => {
      throw new Error("数据库不可用");
    };
    client.createChatSession = failing;
    const { result } = renderChat(client, null);

    await act(async () => {
      await result.current.send("你好");
    });

    expect(result.current.error).toBe("数据库不可用");
    expect(order).not.toContain("stream");
  });
});
