import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { ApiProvider } from "../api/ApiContext";
import type { ApiClient } from "../api/client";
import { AppShell } from "./AppShell";
import styles from "./AppShell.module.css";

// CSS Modules 的索引签名在 strict 下是 string | undefined，取一次具体类名。
const CONTENT_FULL_CLASS = styles.contentFull ?? "";
// 登录门变体：页壳铺整视口渐变，顶栏透明叠在渐变上，内容通栏。
const SHELL_GATE_CLASS = styles.shellGate ?? "";
const TOPBAR_GATE_CLASS = styles.topbarGate ?? "";
const CONTENT_GATE_CLASS = styles.contentGate ?? "";

function fakeClient(): ApiClient {
  return {
    currentPrincipal: () => Promise.resolve({ user_id: "u1", roles: [] }),
    logout: () => Promise.resolve(),
  } as unknown as ApiClient;
}

function anonymousClient(): ApiClient {
  return {
    currentPrincipal: () => Promise.reject(new Error("not signed in")),
    logout: () => Promise.resolve(),
  } as unknown as ApiClient;
}

function renderShell(initialPath: string, client: ApiClient = fakeClient()) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ApiProvider client={client}>
        <MemoryRouter initialEntries={[initialPath]}>
          <AppShell>
            <Routes>
              <Route path="/chat" element={<p>对话内容</p>} />
              <Route path="/interview" element={<p>面试内容</p>} />
              <Route path="/interview/room/:sessionId" element={<p>房间内容</p>} />
              <Route path="/settings/ai" element={<p>设置内容</p>} />
            </Routes>
          </AppShell>
        </MemoryRouter>
      </ApiProvider>
    </QueryClientProvider>,
  );
}

describe("AppShell", () => {
  it("marks the nav item of the current route with aria-current", async () => {
    renderShell("/chat");
    await screen.findByText("u1");

    expect(screen.getByRole("link", { name: "对话" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "面试" })).not.toHaveAttribute("aria-current");
    expect(screen.getByRole("link", { name: "AI 设置" })).not.toHaveAttribute("aria-current");
  });

  it("keeps the section highlighted on a nested route", async () => {
    renderShell("/interview/room/s-1");
    await screen.findByText("u1");

    expect(screen.getByRole("link", { name: "面试" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "对话" })).not.toHaveAttribute("aria-current");
  });

  it("makes the content container full-bleed on the chat route", async () => {
    renderShell("/chat");

    const content = (await screen.findByText("对话内容")).parentElement;
    expect(content).toHaveClass(CONTENT_FULL_CLASS);
  });

  it("keeps the content container constrained outside the chat route", async () => {
    renderShell("/interview");

    const content = (await screen.findByText("面试内容")).parentElement;
    expect(content).not.toHaveClass(CONTENT_FULL_CLASS);
  });

  it("spans the gate gradient across the shell and content on a login-gate route", async () => {
    renderShell("/chat", anonymousClient());

    const shell = await waitFor(() => {
      const element = screen.getByRole("link", { name: "better-resume" }).closest("div");
      expect(element).toHaveClass(SHELL_GATE_CLASS);
      return element as HTMLElement;
    });
    expect(shell.querySelector("header")).toHaveClass(TOPBAR_GATE_CLASS);
    expect(screen.getByText("对话内容").parentElement).toHaveClass(CONTENT_GATE_CLASS);
  });

  it("keeps the shell unvaried on a route without the login gate", async () => {
    renderShell("/settings/ai", anonymousClient());

    await screen.findByText("设置内容");
    const topbar = screen.getByRole("link", { name: "better-resume" }).closest("header");
    expect(topbar).not.toHaveClass(TOPBAR_GATE_CLASS);
    expect(screen.getByText("设置内容").parentElement).not.toHaveClass(CONTENT_GATE_CLASS);
    expect(topbar?.parentElement).not.toHaveClass(SHELL_GATE_CLASS);
  });

  it("keeps the shell unvaried on a login-gate route once signed in", async () => {
    renderShell("/chat");
    await screen.findByText("u1");

    const topbar = screen.getByRole("link", { name: "better-resume" }).closest("header");
    expect(topbar).not.toHaveClass(TOPBAR_GATE_CLASS);
    expect((await screen.findByText("对话内容")).parentElement).not.toHaveClass(CONTENT_GATE_CLASS);
    expect(topbar?.parentElement).not.toHaveClass(SHELL_GATE_CLASS);
  });
});
