import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";

import { ApiProvider } from "../api/ApiContext";

import type { ApiClient } from "../api/client";
import { ApiError } from "../api/errors";
import type { ChatMessageView, ChatSessionView, ChatStreamRequest } from "../api/types";
import type { ChatStreamHandlers } from "../api/sse";
import { useChatStore } from "../chat/store";
import { ChatPage } from "./ChatPage";

const SESSION: ChatSessionView = {
  id: "s-1",
  kind: "chat",
  title: "第一个会话",
  model_ref: null,
  message_count: 2,
  created_at: "2026-09-13T00:00:00Z",
  updated_at: "2026-09-13T00:00:00Z",
};

function messageView(seq: number, role: string, content: string, reasoning?: string): ChatMessageView {
  return {
    id: `m-${seq}`,
    seq,
    role,
    client_message_id: role === "user" ? `cm-${seq}` : null,
    content,
    reasoning: reasoning ?? null,
    token_count: null,
    error_message: null,
    created_at: "2026-09-13T00:00:00Z",
  };
}

interface FakeClient {
  client: ApiClient;
  streams: Array<{ sessionId: string; body: ChatStreamRequest; handlers: ChatStreamHandlers }>;
  authed: { value: boolean };
}

function fakeClient(options: { authenticated?: boolean; history?: ChatMessageView[] } = {}): FakeClient {
  const authed = { value: options.authenticated ?? true };
  const streams: FakeClient["streams"] = [];

  const client = {
    currentPrincipal: () =>
      authed.value
        ? Promise.resolve({ user_id: "u1", roles: [] })
        : Promise.reject(new ApiError("not authenticated", { kind: "unauthorized", status: 401 })),
    devLogin: () => {
      authed.value = true;
      return Promise.resolve({ user_id: "demo", roles: [] });
    },
    logout: () => {
      authed.value = false;
      return Promise.resolve();
    },
    listChatSessions: () => Promise.resolve([SESSION]),
    listChatMessages: () => Promise.resolve(options.history ?? []),
    listModels: () =>
      Promise.resolve([
        {
          name: "deepseek-flash",
          model_id: "deepseek-flash",
          provider: "deepseek",
          supports_reasoning: true,
          configured: true,
          is_default: true,
        },
        {
          name: "deepseek-v4-pro",
          model_id: "deepseek-v4-pro",
          provider: "deepseek",
          supports_reasoning: true,
          configured: false,
          is_default: false,
        },
      ]),
    createChatSession: () => Promise.resolve(SESSION),
    deleteChatSession: () => Promise.resolve(),
    streamChat: (
      sessionId: string,
      body: ChatStreamRequest,
      handlers: ChatStreamHandlers,
    ) => {
      streams.push({ sessionId, body, handlers });
      return Promise.resolve();
    },
  } as unknown as ApiClient;

  return { client, streams, authed };
}

function renderPage(client: ApiClient, initialPath = "/chat/s-1") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ApiProvider client={client}>
        <MemoryRouter initialEntries={[initialPath]}>
          <Routes>
            <Route path="/chat" element={<ChatPage />} />
            <Route path="/chat/:sessionId" element={<ChatPage />} />
          </Routes>
        </MemoryRouter>
      </ApiProvider>
    </QueryClientProvider>,
  );
}

function typeAndSend(text: string): void {
  const box = screen.getByLabelText("输入消息");
  fireEvent.change(box, { target: { value: text } });
  fireEvent.keyDown(box, { key: "Enter" });
}

describe("ChatPage", () => {
  beforeEach(() => {
    useChatStore.getState().reset();
  });

  it("shows the dev session gate when unauthenticated", async () => {
    const { client } = fakeClient({ authenticated: false });
    renderPage(client);

    expect(await screen.findByRole("button", { name: "进入" })).toBeInTheDocument();
  });

  it("replays history from the server with a collapsible reasoning panel", async () => {
    const { client } = fakeClient({
      history: [
        messageView(1, "user", "什么是二分查找"),
        messageView(2, "assistant", "在有序数组中折半查找", "先确认数组有序"),
      ],
    });
    renderPage(client);

    expect(await screen.findByText("什么是二分查找")).toBeInTheDocument();
    expect(screen.getByText("在有序数组中折半查找")).toBeInTheDocument();

    const toggle = screen.getByRole("button", { name: /深度思考/ });
    expect(screen.getByRole("region", { name: "深度思考" })).toHaveTextContent("先确认数组有序");

    fireEvent.click(toggle);
    expect(screen.queryByRole("region", { name: "深度思考" })).not.toBeInTheDocument();
  });

  it("sends a turn and types the answer out", async () => {
    const { client, streams } = fakeClient({ history: [] });
    renderPage(client);

    await screen.findByRole("button", { name: "发送" });
    typeAndSend("你好");

    expect(await screen.findByText("你好")).toBeInTheDocument();
    await waitFor(() => {
      expect(streams).toHaveLength(1);
    });

    act(() => {
      streams[0]?.handlers.onReasoning?.("先想");
      streams[0]?.handlers.onContent?.("你");
      streams[0]?.handlers.onContent?.("好");
    });

    await waitFor(() => {
      expect(screen.getByRole("region", { name: "深度思考" })).toHaveTextContent("先想");
    });
    await waitFor(() => {
      expect(screen.getByLabelText("AI 回答")).toHaveTextContent("你好");
    });
    expect(screen.getByRole("button", { name: "停止生成" })).toBeInTheDocument();

    act(() => {
      streams[0]?.handlers.onDone?.({ finish_reason: "stop" });
    });

    expect(await screen.findByRole("button", { name: "发送" })).toBeInTheDocument();
  });

  it("marks the answer as cancelled when the user stops generation", async () => {
    const { client, streams } = fakeClient({ history: [] });
    renderPage(client);

    await screen.findByRole("button", { name: "发送" });
    typeAndSend("长问题");
    await waitFor(() => {
      expect(streams).toHaveLength(1);
    });

    act(() => {
      streams[0]?.handlers.onContent?.("半句");
    });
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "停止生成" })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "停止生成" }));

    expect(await screen.findByText("已取消")).toBeInTheDocument();
  });

  it("explains an overload failure and retries the same turn", async () => {
    const { client, streams } = fakeClient({ history: [] });
    renderPage(client);

    await screen.findByRole("button", { name: "发送" });
    typeAndSend("会被限流的问题");
    await waitFor(() => {
      expect(streams).toHaveLength(1);
    });

    act(() => {
      streams[0]?.handlers.onError?.(
        new ApiError("rate limit exceeded for read", {
          kind: "rate_limited",
          status: 429,
          retryAfterSeconds: 2,
        }),
      );
    });

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("服务繁忙，请 2 秒后重试");

    fireEvent.click(screen.getByRole("button", { name: "重试" }));

    await waitFor(() => {
      expect(streams).toHaveLength(2);
    });
    expect(streams[1]?.body.content).toBe("会被限流的问题");
  });

  it("shows the empty state when a session has no messages", async () => {
    const { client } = fakeClient({ history: [] });
    renderPage(client);

    expect(await screen.findByText("还没有消息")).toBeInTheDocument();
  });
});
