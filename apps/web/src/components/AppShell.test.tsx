import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { ApiProvider } from "../api/ApiContext";
import type { ApiClient } from "../api/client";
import { AppShell } from "./AppShell";
import styles from "./AppShell.module.css";

// CSS Modules 的索引签名在 strict 下是 string | undefined，取一次具体类名。
const SIDEBAR_COLLAPSED_CLASS = styles.sidebarCollapsed ?? "";
const SHELL_CLASS = styles.shell ?? "";
const SHELL_GATE_CLASS = styles.shellGate ?? "";
const SIDEBAR_GATE_CLASS = styles.sidebarGate ?? "";
const CONTENT_CLASS = styles.content ?? "";

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
              <Route path="/coming-soon/user-manual" element={<p>手册内容</p>} />
            </Routes>
          </AppShell>
        </MemoryRouter>
      </ApiProvider>
    </QueryClientProvider>,
  );
}

function sidebarOf(): HTMLElement {
  return screen.getByRole("complementary", { name: "侧边栏" });
}

/** 登录查询落定前页壳已渲染品牌区，账号行出现才代表会话状态已就绪。 */
async function signedIn(): Promise<void> {
  await screen.findByText("账号: u1");
}

describe("AppShell", () => {
  it("renders the brand heading with the product name", async () => {
    renderShell("/interview");
    await signedIn();

    expect(screen.getByRole("heading", { name: "better-resume" })).toBeInTheDocument();
  });

  it("lists the primary and secondary navigation in one landmark each", async () => {
    renderShell("/interview");
    await signedIn();

    expect(screen.getByRole("navigation", { name: "主导航" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "次级导航" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "面试辅助" })).toHaveAttribute(
      "href",
      "/coming-soon/interview-assist",
    );
    expect(screen.getByRole("link", { name: "定制知识库" })).toHaveAttribute(
      "href",
      "/coming-soon/knowledge-base",
    );
    expect(screen.getByRole("link", { name: "模拟面试" })).toHaveAttribute("href", "/interview");
    expect(screen.getByRole("link", { name: "我的简历" })).toHaveAttribute("href", "/resumes");
    expect(screen.getByRole("link", { name: "用户手册" })).toHaveAttribute(
      "href",
      "/coming-soon/user-manual",
    );
    expect(screen.getByRole("link", { name: "最新更新" })).toHaveAttribute(
      "href",
      "/coming-soon/whats-new",
    );
  });

  it("marks the nav item of the current route with aria-current", async () => {
    renderShell("/interview");
    await signedIn();

    expect(screen.getByRole("link", { name: "模拟面试" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "我的简历" })).not.toHaveAttribute("aria-current");
    expect(screen.getByRole("link", { name: "面试辅助" })).not.toHaveAttribute("aria-current");
  });

  it("keeps the section highlighted on a nested route", async () => {
    renderShell("/interview/room/s-1");
    await signedIn();

    expect(screen.getByRole("link", { name: "模拟面试" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "我的简历" })).not.toHaveAttribute("aria-current");
  });

  it("collapses the sidebar from the brand-row toggle and restores it", async () => {
    renderShell("/interview");
    await signedIn();

    const sidebar = sidebarOf();
    expect(sidebar).not.toHaveClass(SIDEBAR_COLLAPSED_CLASS);

    await userEvent.click(screen.getByRole("button", { name: "收起侧边栏" }));

    expect(sidebarOf()).toHaveClass(SIDEBAR_COLLAPSED_CLASS);
    expect(screen.getByRole("button", { name: "展开侧边栏" })).toHaveAttribute(
      "aria-expanded",
      "false",
    );

    await userEvent.click(screen.getByRole("button", { name: "展开侧边栏" }));

    expect(sidebarOf()).not.toHaveClass(SIDEBAR_COLLAPSED_CLASS);
  });

  it("shows the account row with the session user and a logout action", async () => {
    renderShell("/interview");

    expect(await screen.findByText("账号: u1")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "退出" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "AI 设置" })).toHaveAttribute("href", "/settings/ai");
  });

  it("logs out through the account row", async () => {
    const client = fakeClient();
    const logout = vi.spyOn(client, "logout");
    renderShell("/interview", client);
    await screen.findByText("账号: u1");

    await userEvent.click(screen.getByRole("button", { name: "退出" }));

    expect(logout).toHaveBeenCalledTimes(1);
  });

  it("shows the anonymous account row without a logout action", async () => {
    renderShell("/settings/ai", anonymousClient());

    expect(await screen.findByText("未登录")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "退出" })).not.toBeInTheDocument();
  });

  it("hides the chat bubble on the chat route", async () => {
    renderShell("/chat");
    await signedIn();

    expect(screen.queryByRole("link", { name: "打开对话" })).not.toBeInTheDocument();
  });

  it("hides the chat bubble on a route behind the login gate", async () => {
    renderShell("/interview", anonymousClient());

    // 登录门落定：门态下点气泡只会撞回同一扇门，入口不该出现。
    await waitFor(() => {
      expect(document.querySelector(`.${SHELL_CLASS}`)).toHaveClass(SHELL_GATE_CLASS);
    });

    expect(screen.queryByRole("link", { name: "打开对话" })).not.toBeInTheDocument();
  });

  it("opens the chat route from the floating bubble", async () => {
    renderShell("/interview");
    await signedIn();

    expect(screen.getByRole("link", { name: "打开对话" })).toHaveAttribute("href", "/chat");
  });

  it("keeps the content column full width so the chat session sidebar stays flush", async () => {
    renderShell("/chat");
    await signedIn();

    const shell = document.querySelector(`.${SHELL_CLASS}`);
    expect(shell).not.toBeNull();

    // 内容列是外壳的直接子节点、与页壳侧栏同级：对话页自己的会话侧栏贴边铺满靠的就是这层结构，
    // 多包一层或用非内容列类都会让它缩进。
    const main = screen.getByRole("main");
    expect(main).toHaveClass(CONTENT_CLASS);
    expect(main.parentElement).toBe(shell);
    expect(shell?.firstElementChild).toBe(sidebarOf());
  });

  it("spans the gate gradient across the shell and empties the sidebar on a login-gate route", async () => {
    renderShell("/chat", anonymousClient());

    await screen.findByRole("link", { name: "better-resume" });
    const shell = document.querySelector(`.${SHELL_CLASS}`);
    expect(shell).not.toBeNull();

    await waitFor(() => {
      expect(shell).toHaveClass(SHELL_GATE_CLASS);
    });
    expect(shell?.querySelector("aside")).toHaveClass(SIDEBAR_GATE_CLASS);
    expect(screen.queryByRole("navigation", { name: "主导航" })).not.toBeInTheDocument();
    expect(screen.queryByText("未登录")).not.toBeInTheDocument();
    expect(screen.getByText("对话内容")).toBeInTheDocument();
  });

  it("keeps the shell unvaried on a route without the login gate", async () => {
    renderShell("/settings/ai", anonymousClient());

    await screen.findByText("设置内容");
    const shell = document.querySelector(`.${SHELL_CLASS}`);
    expect(shell).not.toHaveClass(SHELL_GATE_CLASS);
    expect(screen.getByRole("navigation", { name: "主导航" })).toBeInTheDocument();
  });

  it("keeps the shell unvaried on a login-gate route once signed in", async () => {
    renderShell("/chat");
    await signedIn();

    const shell = document.querySelector(`.${SHELL_CLASS}`);
    expect(shell).not.toHaveClass(SHELL_GATE_CLASS);
    expect(screen.getByRole("navigation", { name: "主导航" })).toBeInTheDocument();
  });
});
