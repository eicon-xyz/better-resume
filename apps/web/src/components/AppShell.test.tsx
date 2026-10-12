import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { ApiProvider } from "../api/ApiContext";
import type { ApiClient } from "../api/client";
import { AppShell } from "./AppShell";

function fakeClient(): ApiClient {
  return {
    currentPrincipal: () => Promise.resolve({ user_id: "u1", roles: [] }),
    logout: () => Promise.resolve(),
  } as unknown as ApiClient;
}

function renderShell(initialPath: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ApiProvider client={fakeClient()}>
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
});
