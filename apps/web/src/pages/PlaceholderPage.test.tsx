import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { PlaceholderPage } from "./PlaceholderPage";

function LocationProbe() {
  const { pathname } = useLocation();
  return <p>当前位置：{pathname}</p>;
}

function renderPlaceholder(slug: string) {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={[`/coming-soon/${slug}`]}>
        <Routes>
          <Route path="/coming-soon/:slug" element={<PlaceholderPage />} />
          <Route path="/interview" element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("PlaceholderPage", () => {
  it("names the requested feature and explains it is not live yet", () => {
    renderPlaceholder("interview-assist");

    expect(screen.getByRole("heading", { name: "面试辅助" })).toBeInTheDocument();
    expect(screen.getByText("敬请期待")).toBeInTheDocument();
    expect(screen.getByText(/尚未上线/)).toBeInTheDocument();
  });

  it("names the resume import entry", () => {
    renderPlaceholder("resume-import");

    expect(screen.getByRole("heading", { name: "导入简历" })).toBeInTheDocument();
  });

  it("falls back to a generic name for an unknown slug", () => {
    renderPlaceholder("not-a-feature");

    expect(screen.getByRole("heading", { name: "该功能" })).toBeInTheDocument();
  });

  it("returns to the interview page from the back button", async () => {
    renderPlaceholder("knowledge-base");

    await userEvent.click(screen.getByRole("button", { name: "返回模拟面试" }));

    expect(await screen.findByText("当前位置：/interview")).toBeInTheDocument();
  });
});
