import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { QuestionBatchView } from "../../api/types";
import { degradedNotice } from "../../interview/degraded";
import { ResumePreviewCard } from "./ResumePreviewCard";

const BATCH: QuestionBatchView = {
  session: {
    id: "s-1",
    status: "ready",
    interview_type: "auto",
    question_count: 1,
    resume_score: 66,
    created_at: "2026-10-11T00:00:00Z",
    updated_at: "2026-10-11T00:00:00Z",
  },
  questions: [
    {
      question_no: "1",
      topic_no: 1,
      follow_up_index: 0,
      kind: "main",
      category: "fundamentals",
      text: "请说明缓存穿透的防护手段",
      focus_points: ["布隆过滤器"],
    },
  ],
  suggestions: [],
  flow: {
    status: "asking",
    current_question_no: "1",
    total_questions: 1,
    follow_up_count: 0,
    max_follow_up: 2,
  },
  replayed: false,
  degraded: true,
  degraded_reasons: ["corpus_no_match"],
};

describe("ResumePreviewCard", () => {
  it("shows the questions and their focus points", () => {
    render(<ResumePreviewCard batch={{ ...BATCH, degraded: false, degraded_reasons: [] }} />);

    expect(screen.getByText("请说明缓存穿透的防护手段")).toBeInTheDocument();
    expect(screen.getByText(/考察：布隆过滤器/)).toBeInTheDocument();
  });

  it("says out loud when the generation degraded", () => {
    render(<ResumePreviewCard batch={BATCH} />);

    expect(screen.getByRole("alert")).toHaveTextContent("没有匹配到八股语料");
  });

  it("falls back to a generic notice for an unknown code", () => {
    expect(degradedNotice(["something_new"])).toBe("本次出题已降级，部分参考数据不可用。");
    expect(degradedNotice([])).toBeNull();
  });
});
