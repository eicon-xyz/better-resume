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
  summary_pending: false,
};

/** Two main questions plus a follow-up: enough structure to pin the grouping. */
const GROUPED: InterviewReportView = {
  ...REPORT,
  turns: [
    {
      question_no: "1",
      topic_no: 1,
      follow_up_index: 0,
      kind: "main",
      question: "主问题一",
      answer: "回答一",
      score: 70,
      feedback: "还行",
      missing_points: [],
      follow_up_reason: null,
    },
    {
      question_no: "1-F1",
      topic_no: 1,
      follow_up_index: 1,
      kind: "follow_up",
      question: "追问一",
      answer: "回答一追",
      score: 65,
      feedback: "继续",
      missing_points: [],
      follow_up_reason: null,
    },
    {
      question_no: "2",
      topic_no: 2,
      follow_up_index: 0,
      kind: "main",
      question: "主问题二",
      answer: "回答二",
      score: 80,
      feedback: "不错",
      missing_points: [],
      follow_up_reason: null,
    },
  ],
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

  it("scores every category and marks thin samples", async () => {
    renderReport(
      fakeClient({
        ...REPORT,
        categories: [
          { key: "fundamentals", label: "八股", count: 0, score: null, comment: "样本不足" },
          {
            key: "project",
            label: "项目",
            count: 3,
            score: 78.3,
            comment: "基本掌握，细节还可以再深",
          },
          { key: "internship", label: "实习", count: 1, score: null, comment: "样本不足" },
        ],
      }),
    );

    expect(await screen.findByText("按类给分")).toBeInTheDocument();
    expect(screen.getByLabelText("项目得分")).toHaveTextContent("78.3");
    expect(screen.getAllByText("样本不足")).toHaveLength(2);
    expect(screen.getByText("基本掌握，细节还可以再深")).toBeInTheDocument();
  });

  it("shows an empty state when there is no report yet", async () => {
    renderReport(
      fakeClient(new ApiError("report for s-1 is not ready", { kind: "not_found", status: 404 })),
    );

    expect(await screen.findByText("还没有报告")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "回到面试入口" }));
    expect(await screen.findByText("面试入口")).toBeInTheDocument();
  });

  it("opens only the first question group by default", async () => {
    renderReport(fakeClient(GROUPED));

    const first = await screen.findByRole("button", { name: "第 1 题 · 主问题一" });
    const second = screen.getByRole("button", { name: "第 2 题 · 主问题二" });

    expect(first).toHaveAttribute("aria-expanded", "true");
    expect(second).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByText("主问题一")).toBeInTheDocument();
    expect(screen.queryByText("主问题二")).not.toBeInTheDocument();
  });

  it("toggles one question group from its header", async () => {
    renderReport(fakeClient(GROUPED));

    const first = await screen.findByRole("button", { name: "第 1 题 · 主问题一" });
    fireEvent.click(first);
    expect(first).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("主问题一")).not.toBeInTheDocument();

    fireEvent.click(first);
    expect(first).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("主问题一")).toBeInTheDocument();
  });

  it("expands and collapses every question group at once", async () => {
    renderReport(fakeClient(GROUPED));

    expect(await screen.findByRole("button", { name: "第 2 题 · 主问题二" })).toHaveAttribute(
      "aria-expanded",
      "false",
    );

    fireEvent.click(screen.getByRole("button", { name: "全部展开" }));
    expect(screen.getByRole("button", { name: "第 2 题 · 主问题二" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
    expect(screen.getByText("主问题二")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "全部收起" }));
    expect(screen.getByRole("button", { name: "第 2 题 · 主问题二" })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
    expect(screen.queryByText("主问题二")).not.toBeInTheDocument();
  });

  it("shows a thin-sample badge instead of a score for a category without one", async () => {
    renderReport(
      fakeClient({
        ...REPORT,
        categories: [
          { key: "fundamentals", label: "八股", count: 0, score: null, comment: "样本不足" },
          { key: "project", label: "项目", count: 3, score: 78.3, comment: "基本掌握" },
        ],
      }),
    );

    expect(await screen.findByText("按类给分")).toBeInTheDocument();
    expect(screen.getByLabelText("项目得分")).toHaveTextContent("78.3");
    expect(screen.queryByLabelText("八股得分")).not.toBeInTheDocument();
    expect(screen.getByText("样本不足")).toBeInTheDocument();
  });

  it("offers a fresh interview from the header", async () => {
    renderReport(fakeClient());

    const button = await screen.findByRole("button", { name: "再面一次" });
    fireEvent.click(button);

    expect(await screen.findByText("面试入口")).toBeInTheDocument();
  });
});
