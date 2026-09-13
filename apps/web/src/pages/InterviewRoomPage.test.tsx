import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiProvider } from "../api/ApiContext";
import type { ApiClient } from "../api/client";
import { ApiError } from "../api/errors";
import type { AnswerSubmitView, GeneratedQuestionView } from "../api/types";
import { useRoomStore } from "../interview/roomStore";
import { InterviewRoomPage } from "./InterviewRoomPage";

const QUESTION_1: GeneratedQuestionView = {
  question_no: "1",
  topic_no: 1,
  follow_up_index: 0,
  kind: "main",
  text: "讲讲你最有挑战的项目",
  focus_points: ["取舍", "量化"],
};

const QUESTION_2: GeneratedQuestionView = {
  question_no: "2",
  topic_no: 2,
  follow_up_index: 0,
  kind: "main",
  text: "如何做性能压测",
  focus_points: ["指标"],
};

const FOLLOW_UP: GeneratedQuestionView = {
  question_no: "1-F1",
  topic_no: 1,
  follow_up_index: 1,
  kind: "follow_up",
  text: "当时为什么选这个方案？",
  focus_points: ["取舍"],
};

function restoreView(question: GeneratedQuestionView, answered = 0) {
  return {
    session: {
      id: "s-1",
      status: answered > 0 ? "in_progress" : "ready",
      interview_type: null,
      question_count: 2,
      resume_score: 70,
      created_at: "2026-09-13T00:00:00Z",
      updated_at: "2026-09-13T00:00:00Z",
    },
    flow: {
      status: "asking",
      current_question_no: question.question_no,
      total_questions: 2,
      follow_up_count: 0,
      max_follow_up: 2,
    },
    current_question: question,
    answered,
    total_questions: 2,
    last_answer: null,
    derived: false,
  };
}

function submitView(options: {
  nextQuestion: GeneratedQuestionView | null;
  nextAction: string;
  score?: number;
  followUpReason?: string;
}): AnswerSubmitView {
  return {
    session: {
      id: "s-1",
      status: "in_progress",
      interview_type: null,
      question_count: 2,
      resume_score: 70,
      created_at: "2026-09-13T00:00:00Z",
      updated_at: "2026-09-13T00:00:00Z",
    },
    answer: {
      question_no: "1",
      score: options.score ?? 84,
      feedback: "结构清晰，但缺少量化",
      missing_points: ["量化"],
      follow_up_needed: Boolean(options.followUpReason),
      follow_up_reason: options.followUpReason ?? null,
      rule_version: "m2.1",
      error_message: null,
    },
    flow: {
      status: options.nextAction === "follow_up" ? "follow_up" : "asking",
      current_question_no: options.nextQuestion?.question_no ?? null,
      total_questions: 2,
      follow_up_count: options.nextAction === "follow_up" ? 1 : 0,
      max_follow_up: 2,
    },
    next_action: options.nextAction,
    next_question_no: options.nextQuestion?.question_no ?? null,
    next_question: options.nextQuestion,
    replayed: false,
  };
}

function fakeClient(overrides: Partial<ApiClient> = {}) {
  return {
    restoreInterview: vi.fn(() => Promise.resolve(restoreView(QUESTION_1))),
    submitInterviewAnswer: vi.fn(() =>
      Promise.resolve(submitView({ nextQuestion: QUESTION_2, nextAction: "next_question" })),
    ),
    finishInterview: vi.fn(() => Promise.resolve({ session: { id: "s-1" }, overall_score: 80 })),
    ...overrides,
  } as unknown as ApiClient;
}

function renderRoom(client: ApiClient) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ApiProvider client={client}>
        <MemoryRouter initialEntries={["/interview/room/s-1"]}>
          <Routes>
            <Route path="/interview/room/:sessionId" element={<InterviewRoomPage />} />
            <Route path="/interview/report/:sessionId" element={<p>报告页已打开</p>} />
            <Route path="/interview" element={<p>入口页</p>} />
          </Routes>
        </MemoryRouter>
      </ApiProvider>
    </QueryClientProvider>,
  );
}

function answer(text: string) {
  fireEvent.change(screen.getByLabelText("你的回答"), { target: { value: text } });
  fireEvent.click(screen.getByRole("button", { name: "提交回答" }));
}

describe("InterviewRoomPage", () => {
  beforeEach(() => {
    useRoomStore.getState().reset();
  });

  it("restores the session and shows the current question", async () => {
    renderRoom(fakeClient());

    expect(await screen.findByText("讲讲你最有挑战的项目")).toBeInTheDocument();
    expect(screen.getByText("考察要点：取舍、量化")).toBeInTheDocument();
    expect(screen.getByText("已答 0 / 2 题")).toBeInTheDocument();
  });

  it("submits an answer once, shows feedback and moves on", async () => {
    const client = fakeClient();
    renderRoom(client);

    await screen.findByText("讲讲你最有挑战的项目");
    answer("我重构了写入链路");

    expect(await screen.findByText("结构清晰，但缺少量化")).toBeInTheDocument();
    expect(screen.getByText("已答 1 / 2 题")).toBeInTheDocument();
    expect(await screen.findByText("如何做性能压测")).toBeInTheDocument();

    const [sessionId, body] = vi.mocked(client.submitInterviewAnswer).mock.calls[0] ?? [];
    expect(sessionId).toBe("s-1");
    expect(body).toMatchObject({ question_no: "1", answer: "我重构了写入链路" });
    expect(body?.request_id).toBeTruthy();
  });

  it("ignores a double click within the debounce window", async () => {
    const client = fakeClient();
    renderRoom(client);

    await screen.findByText("讲讲你最有挑战的项目");
    const button = screen.getByRole("button", { name: "提交回答" });
    fireEvent.change(screen.getByLabelText("你的回答"), { target: { value: "第一次" } });
    fireEvent.click(button);
    fireEvent.change(screen.getByLabelText("你的回答"), { target: { value: "第二次" } });
    fireEvent.click(button);

    await waitFor(() => {
      expect(vi.mocked(client.submitInterviewAnswer)).toHaveBeenCalledTimes(1);
    });
  });

  it("marks a follow-up question with its reason", async () => {
    const client = fakeClient({
      submitInterviewAnswer: vi.fn(() =>
        Promise.resolve(
          submitView({
            nextQuestion: FOLLOW_UP,
            nextAction: "follow_up",
            score: 42,
            followUpReason: "LOW_SCORE",
          }),
        ),
      ),
    });
    renderRoom(client);

    await screen.findByText("讲讲你最有挑战的项目");
    answer("答得很浅");

    expect(await screen.findByText("当时为什么选这个方案？")).toBeInTheDocument();
    expect(screen.getByText("追问 · 上一题得分偏低")).toBeInTheDocument();
    expect(screen.getByLabelText("当前题号")).toHaveTextContent("1-F1");
  });

  it("keeps the question answerable when the submission fails", async () => {
    let attempt = 0;
    const client = fakeClient({
      submitInterviewAnswer: vi.fn(() => {
        attempt += 1;
        if (attempt === 1) {
          return Promise.reject(new ApiError("上游超时", { kind: "server", status: 502 }));
        }
        return Promise.resolve(submitView({ nextQuestion: QUESTION_2, nextAction: "next_question" }));
      }),
    });
    renderRoom(client);

    await screen.findByText("讲讲你最有挑战的项目");
    answer("第一次会失败");

    expect(await screen.findByRole("alert")).toHaveTextContent("上游超时");
    expect(screen.getByText("讲讲你最有挑战的项目")).toBeInTheDocument();

    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 300)); // leave the debounce window
    });
    answer("第二次成功");

    expect(await screen.findByText("如何做性能压测")).toBeInTheDocument();
    expect(vi.mocked(client.submitInterviewAnswer)).toHaveBeenCalledTimes(2);
  });

  it("keeps the typed answer when the backend sheds load", async () => {
    const client = fakeClient({
      submitInterviewAnswer: vi.fn(() =>
        Promise.reject(
          new ApiError("rate limit exceeded for answer", {
            kind: "rate_limited",
            status: 429,
            retryAfterSeconds: 1,
          }),
        ),
      ),
    });
    renderRoom(client);

    await screen.findByText("讲讲你最有挑战的项目");
    fireEvent.change(screen.getByLabelText("你的回答"), { target: { value: "别弄丢我" } });
    fireEvent.click(screen.getByRole("button", { name: "提交回答" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("服务繁忙，请 1 秒后重试");
    expect(alert).toHaveTextContent("本题分数未记录，可直接重试");
    expect(screen.getByLabelText("你的回答")).toHaveValue("别弄丢我");
  });

  it("finishes the interview and navigates to the report", async () => {
    const client = fakeClient();
    renderRoom(client);

    await screen.findByText("讲讲你最有挑战的项目");
    fireEvent.click(screen.getByRole("button", { name: "结束并生成报告" }));

    expect(await screen.findByText("报告页已打开")).toBeInTheDocument();
    expect(client.finishInterview).toHaveBeenCalledWith("s-1");
  });

  it("offers a way back when the session cannot be restored", async () => {
    const client = fakeClient({
      restoreInterview: vi.fn(() =>
        Promise.reject(new ApiError("会话不存在", { kind: "not_found", status: 404 })),
      ),
    });
    renderRoom(client);

    expect(await screen.findByText("无法恢复这场面试")).toBeInTheDocument();
    expect(screen.getByText("会话不存在")).toBeInTheDocument();
  });
});
