import { render, screen } from "@testing-library/react";
import { QueryClient } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";

import type { ApiClient } from "./api/client";
import { App } from "./App";

function fakeClient(): ApiClient {
  return {
    currentPrincipal: () => Promise.resolve({ user_id: "u1", roles: [] }),
    listChatSessions: () => Promise.resolve([]),
    listChatMessages: () => Promise.resolve([]),
    listModels: () => Promise.resolve([]),
    listInterviewSessions: () => Promise.resolve([]),
    listScenes: () => Promise.resolve([]),
  } as unknown as ApiClient;
}

function renderApp(initialPath = "/") {
  window.history.pushState({}, "", initialPath);
  return render(<App client={fakeClient()} queryClient={new QueryClient()} />);
}

describe("App", () => {
  it("renders the chat shell for an authenticated visitor", async () => {
    renderApp("/chat");

    expect(await screen.findByRole("heading", { name: "better-resume" })).toBeInTheDocument();
    expect(await screen.findByText("还没有消息")).toBeInTheDocument();
  });

  it("sends the root route to the interview page", async () => {
    renderApp("/");

    expect(await screen.findByRole("heading", { name: "模拟面试" })).toBeInTheDocument();
  });

  it("keeps the six existing route meanings", async () => {
    renderApp("/settings/ai");

    expect(await screen.findByRole("heading", { name: "AI 设置" })).toBeInTheDocument();
  });

  it("renders the resume library route", async () => {
    renderApp("/resumes");

    expect(await screen.findByRole("heading", { name: "我的简历" })).toBeInTheDocument();
  });

  it("renders a coming-soon placeholder for a pending feature", async () => {
    renderApp("/coming-soon/knowledge-base");

    expect(await screen.findByRole("heading", { name: "定制知识库" })).toBeInTheDocument();
    expect(await screen.findByText("敬请期待")).toBeInTheDocument();
  });
});
