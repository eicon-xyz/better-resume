import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { ApiProvider } from "../api/ApiContext";
import type { ApiClient } from "../api/client";
import { ApiError } from "../api/errors";
import type { InterviewReportView } from "../api/types";
import { InterviewReportPage } from "./InterviewReportPage";

const REPORT: InterviewReportView = {
  session: {
    id: "s-1",
    status: "finished",
    interview_type: null,
    question_count: 2,
    resume_score: 70,
    created_at: "2026-09-13T00:00:00Z",
    updated_at: "2026-09-13T00:00:00Z",
  },
  overall_score: 72.5,
  dimensions: [
    { key: "accuracy", label: "准确性", score: 80 },
    { key: "depth", label: "深度", score: 60 },
    { key: "coverage", label: "要点覆盖", score: 40 },
    { key: "completeness", label: "完成度", score: 100 },
  ],
  turns: [
    {
      question_no: "1",
      topic_no: 1,
      follow_up_index: 0,
      kind: "main",
      question: "讲讲你的项目",
      answer: "我重构了写入链路",
      score: 72.5,
      feedback: "结构清晰",
      missing_points: ["量化"],
      follow_up_reason: "MISSING_POINTS",
    },
    {
      question_no: "1-F1",
      topic_no: 1,
      follow_up_index: 1,
      kind: "follow_up",
      question: "当时为什么这么选？",
      answer: "因为写放大",
      score: 60,
      feedback: "还差一点",
      missing_points: ["取舍"],
      follow_up_reason: null,
    },
  ],
  suggestions: ["补充量化结果"],
  summary: "整体不错，细节可再展开。",
  llm_summary_used: true,
};

function fakeClient(report: InterviewReportView | Error = REPORT) {
  return {
    getInterviewReport: vi.fn(() =>
      report instanceof Error ? Promise.reject(report) : Promise.resolve(report),
    ),
  } as unknown as ApiClient;
}

function renderReport(client: ApiClient) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ApiProvider client={client}>
        <MemoryRouter initialEntries={["/interview/report/s-1"]}>
          <Routes>
            <Route path="/interview/report/:sessionId" element={<InterviewReportPage />} />
            <Route path="/interview" element={<p>面试入口</p>} />
            <Route path="/chat" element={<p>对话页</p>} />
          </Routes>
        </MemoryRouter>
      </ApiProvider>
    </QueryClientProvider>,
  );
}

describe("InterviewReportPage", () => {
  it("shows the overall score and the four radar dimensions", async () => {
    renderReport(fakeClient());

    expect(await screen.findByLabelText("综合得分")).toHaveTextContent("72.5");
    const radar = screen.getByTestId("radar-chart");
    expect(radar).toHaveAccessibleName("能力雷达");
    for (const label of ["准确性", "深度", "要点覆盖", "完成度"]) {
      expect(screen.getByText(new RegExp(`^${label}`))).toBeInTheDocument();
    }
    expect(radar.querySelectorAll("polygon[data-ring]")).toHaveLength(4);
  });

  it("replays every turn including the follow-up", async () => {
    renderReport(fakeClient());

    expect(await screen.findByText("讲讲你的项目")).toBeInTheDocument();
    expect(screen.getByText("我的回答：我重构了写入链路")).toBeInTheDocument();
    expect(screen.getByText("当时为什么这么选？")).toBeInTheDocument();
    expect(screen.getByText("追问")).toBeInTheDocument();
    expect(screen.getByLabelText("回放题号 1-F1")).toHaveTextContent("1-F1");
    expect(screen.getByText("缺失要点：量化")).toBeInTheDocument();
  });

  it("explains a missing summary without hiding the numbers", async () => {
    renderReport(fakeClient({ ...REPORT, summary: null, llm_summary_used: false }));

    expect(
      await screen.findByText(/未生成总结（模型不可用或未配置）/),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("综合得分")).toHaveTextContent("72.5");
  });

  it("notes when dimensions had to be synthesised", async () => {
    renderReport(fakeClient({ ...REPORT, dimensions: [] }));

    expect(await screen.findByText(/维度缺失，已用综合分占位展示/)).toBeInTheDocument();
    expect(screen.getByTestId("radar-chart")).toBeInTheDocument();
  });

  it("shows an empty state when there is no report yet", async () => {
    renderReport(
      fakeClient(new ApiError("report for s-1 is not ready", { kind: "not_found", status: 404 })),
    );

    expect(await screen.findByText("还没有报告")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "回到面试入口" }));
    expect(await screen.findByText("面试入口")).toBeInTheDocument();
  });

  it("offers a fresh interview from the header", async () => {
    renderReport(fakeClient());

    const button = await screen.findByRole("button", { name: "再面一次" });
    fireEvent.click(button);

    expect(await screen.findByText("面试入口")).toBeInTheDocument();
  });
});
