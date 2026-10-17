import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { ResumePage } from "./ResumePage";

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/resumes"]}>
      <Routes>
        <Route path="/resumes" element={<ResumePage />} />
        <Route path="/coming-soon/resume-import" element={<p>占位页已打开</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("ResumePage", () => {
  it("renders the header, the import button and the empty state without an api provider", () => {
    renderPage();

    expect(screen.getByRole("heading", { name: "我的简历" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "导入简历 PDF" })).toBeInTheDocument();
    expect(screen.getByText("暂无简历文件")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "导入第一份简历" })).toBeInTheDocument();
  });

  it("navigates to the placeholder page from the header button", async () => {
    renderPage();

    fireEvent.click(screen.getByRole("button", { name: "导入简历 PDF" }));

    expect(await screen.findByText("占位页已打开")).toBeInTheDocument();
  });

  it("navigates to the placeholder page from the empty-state button", async () => {
    renderPage();

    fireEvent.click(screen.getByRole("button", { name: "导入第一份简历" }));

    expect(await screen.findByText("占位页已打开")).toBeInTheDocument();
  });
});
