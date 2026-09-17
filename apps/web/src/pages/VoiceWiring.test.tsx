/**
 * M4-T8: voice answering wiring.
 *
 * Boundaries are injected (capture + socket factories, fake api client) instead of stubbing
 * browser globals: deterministic, and the modules under test stay real.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiProvider } from "../api/ApiContext";
import type { ApiClient } from "../api/client";
import type { GeneratedQuestionView } from "../api/types";
import type { CaptureHandle } from "../audio/capture";
import { mergeTranscript, useTranscriptStore } from "../audio/transcriptStore";
import type { TranscriptionSocket } from "../audio/transcriptionSocket";
import { useTranscription } from "../audio/useTranscription";
import { InterviewRoomPage } from "./InterviewRoomPage";
import { AnswerComposer } from "./interview/RoomParts";

const QUESTION: GeneratedQuestionView = {
  question_no: "1",
  topic_no: 1,
  follow_up_index: 0,
  kind: "main",
  text: "讲讲你最有挑战的项目",
  focus_points: ["取舍"],
};

function restoreView() {
  return {
    session: {
      id: "s-1",
      status: "ready",
      interview_type: null,
      question_count: 1,
      resume_score: 70,
      created_at: "2026-09-14T00:00:00Z",
      updated_at: "2026-09-14T00:00:00Z",
    },
    flow: {
      status: "asking",
      current_question_no: "1",
      total_questions: 1,
      follow_up_count: 0,
      max_follow_up: 2,
    },
    current_question: QUESTION,
    answered: 0,
    total_questions: 1,
    last_answer: null,
    derived: false,
  };
}

function fakeClient(overrides: Partial<ApiClient> = {}): ApiClient {
  return {
    restoreInterview: vi.fn(async () => restoreView()),
    submitInterviewAnswer: vi.fn(async () => ({
      session: { ...restoreView().session, status: "finished" },
      answer: {
        question_no: "1",
        score: 80,
        feedback: "不错",
        missing_points: [],
        follow_up_reason: null,
      },
      next_question: null,
      next_action: "finished",
      flow: { ...restoreView().flow, status: "completed", current_question_no: null },
    })),
    finishInterview: vi.fn(async () => ({ session: restoreView().session, overall_score: 80 })),
    createWsTicket: vi.fn(async () => ({ ticket: "ticket-1", expires_in: 30 })),
    synthesizeSpeech: vi.fn(async () => ({
      url: "/api/v1/media/tts/abc.mp3",
      mime_type: "audio/mpeg",
      cached: false,
      digest: "abc",
    })),
    fetchTtsAudio: vi.fn(async () => new Blob([new Uint8Array([1, 2, 3])])),
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
          </Routes>
        </MemoryRouter>
      </ApiProvider>
    </QueryClientProvider>,
  );
}

function fakeSocket(overrides: Partial<TranscriptionSocket> = {}): TranscriptionSocket {
  return {
    send: vi.fn(),
    finish: vi.fn(),
    stop: vi.fn(),
    queuedFrames: 0,
    reconnects: 0,
    ...overrides,
  };
}

function fakeCapture(): CaptureHandle {
  return { stop: vi.fn(), sampleRate: 16000, usingWorklet: false };
}

/** Minimal consumer of the hook: exercises the controller without the whole page. */
function TranscriptionHarness({
  client,
  onTranscript,
  socket,
  capture,
}: {
  client: ApiClient;
  onTranscript: (text: string) => void;
  socket: TranscriptionSocket;
  capture: CaptureHandle;
}) {
  const [text, setText] = useState("");
  const controller = useTranscription({
    client,
    onTranscript: (next) => {
      onTranscript(next);
      const merged = mergeTranscript(text, next);
      setText(merged.text);
    },
    socketFactory: () => socket,
    captureFactory: async () => capture,
  });
  return (
    <div>
      <button
        type="button"
        onClick={() => {
          void controller.start();
        }}
      >
        开始
      </button>
      <button type="button" onClick={() => controller.stop()}>
        结束
      </button>
      <p data-testid="text">{text}</p>
      <p data-testid="status">{controller.status}</p>
    </div>
  );
}

beforeEach(() => {
  useTranscriptStore.getState().reset();
  // jsdom has no object URLs and no media playback: both are browser boundaries.
  (URL as unknown as { createObjectURL: unknown }).createObjectURL = vi.fn(() => "blob:test/1");
  (URL as unknown as { revokeObjectURL: unknown }).revokeObjectURL = vi.fn();
  vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => undefined);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("useTranscription", () => {
  it("buys a ticket and starts capture without stopping it", async () => {
    const client = fakeClient();
    const capture = fakeCapture();
    render(
      <TranscriptionHarness
        client={client}
        onTranscript={() => undefined}
        socket={fakeSocket()}
        capture={capture}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "开始" }));

    await waitFor(() => {
      expect(client.createWsTicket).toHaveBeenCalledTimes(1);
    });
    expect(capture.stop).not.toHaveBeenCalled();
  });

  it("feeds socket events into the shared store", async () => {
    const client = fakeClient();
    const seen: string[] = [];
    render(
      <TranscriptionHarness
        client={client}
        onTranscript={(text) => seen.push(text)}
        socket={fakeSocket()}
        capture={fakeCapture()}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "开始" }));
    await waitFor(() => {
      expect(client.createWsTicket).toHaveBeenCalled();
    });

    act(() => {
      useTranscriptStore.getState().applyEvent({ kind: "replace", text: "我负责了" });
      useTranscriptStore.getState().applyEvent({ kind: "archive", text: "我负责了订单链路。" });
    });

    await waitFor(() => {
      expect(screen.getByTestId("text")).toHaveTextContent("我负责了订单链路。");
    });
    expect(seen.at(-1)).toBe("我负责了订单链路。");
  });

  it("stops capture and finishes the socket", async () => {
    const client = fakeClient();
    const socket = fakeSocket();
    const capture = fakeCapture();
    render(
      <TranscriptionHarness
        client={client}
        onTranscript={() => undefined}
        socket={socket}
        capture={capture}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "开始" }));
    await waitFor(() => {
      expect(client.createWsTicket).toHaveBeenCalled();
    });

    fireEvent.click(screen.getByRole("button", { name: "结束" }));

    expect(capture.stop).toHaveBeenCalledTimes(1);
    expect(socket.finish).toHaveBeenCalledTimes(1);
  });
});

describe("AnswerComposer", () => {
  it("wires the microphone button and clears only on success", async () => {
    const onSubmit = vi.fn(async () => true);
    const onChange = vi.fn();
    const onToggleRecording = vi.fn();
    render(
      <AnswerComposer
        disabled={false}
        submitting={false}
        value="我负责了订单链路。"
        onChange={onChange}
        onSubmit={onSubmit}
        recording={false}
        onToggleRecording={onToggleRecording}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "语音输入" }));
    expect(onToggleRecording).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: "提交回答" }));
    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledWith("我负责了订单链路。");
    });
    await waitFor(() => {
      expect(onChange).toHaveBeenCalledWith("");
    });
  });

  it("keeps the text when the backend rejects it", async () => {
    const onSubmit = vi.fn(async () => false);
    const onChange = vi.fn();
    render(
      <AnswerComposer
        disabled={false}
        submitting={false}
        value="别弄丢我"
        onChange={onChange}
        onSubmit={onSubmit}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "提交回答" }));

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalled();
    });
    expect(onChange).not.toHaveBeenCalledWith("");
  });

  it("explains a microphone that could not be opened", () => {
    render(
      <AnswerComposer
        disabled={false}
        submitting={false}
        value=""
        onChange={() => undefined}
        onSubmit={() => true}
        recordingError="未获得麦克风权限"
      />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent("未获得麦克风权限");
  });
});

describe("interview room voice wiring", () => {
  it("puts store events into the answer box and submits them", async () => {
    const client = fakeClient();
    renderRoom(client);
    await screen.findByText("讲讲你最有挑战的项目");

    act(() => {
      useTranscriptStore.getState().applyEvent({ kind: "replace", text: "我负责了" });
    });
    await waitFor(() => {
      expect(screen.getByLabelText("你的回答")).toHaveValue("我负责了");
    });
    act(() => {
      useTranscriptStore.getState().applyEvent({ kind: "archive", text: "我负责了订单链路。" });
    });
    await waitFor(() => {
      expect(screen.getByLabelText("你的回答")).toHaveValue("我负责了订单链路。");
    });

    fireEvent.click(screen.getByRole("button", { name: "提交回答" }));

    await waitFor(() => {
      expect(client.submitInterviewAnswer).toHaveBeenCalled();
    });
    expect(vi.mocked(client.submitInterviewAnswer).mock.calls[0]?.[1]).toMatchObject({
      question_no: "1",
      answer: "我负责了订单链路。",
    });
  });
});

describe("interview room realtime partials (P28 regression)", () => {
  it("streams growing partials into the box without ever duplicating them", async () => {
    const client = fakeClient();
    renderRoom(client);
    await screen.findByText("讲讲你最有挑战的项目");

    const box = () => screen.getByLabelText("你的回答");
    const partials = ["我父", "我负责", "我负责过核", "我负责过核心系统的搭建"];
    for (const text of partials) {
      act(() => {
        useTranscriptStore.getState().applyEvent({ kind: "replace", text });
      });
      // the box must show EXACTLY the latest cumulative text, never a concatenation of past ones
      await waitFor(() => {
        expect(box()).toHaveValue(text);
      });
    }

    act(() => {
      useTranscriptStore.getState().applyEvent({ kind: "archive", text: "我负责过核心系统的搭建。" });
    });
    await waitFor(() => {
      expect(box()).toHaveValue("我负责过核心系统的搭建。");
    });

    // second sentence growing on top of the committed one
    for (const live of ["打", "把时间", "把时间从800毫秒降低到了200毫秒"]) {
      act(() => {
        useTranscriptStore.getState().applyEvent({ kind: "replace", text: live });
      });
      await waitFor(() => {
        expect(box()).toHaveValue(`我负责过核心系统的搭建。${live}`);
      });
    }
  });

  it("keeps handwriting inserted mid-stream exactly where it was typed", async () => {
    const client = fakeClient();
    renderRoom(client);
    await screen.findByText("讲讲你最有挑战的项目");

    act(() => {
      useTranscriptStore.getState().applyEvent({ kind: "replace", text: "我负责过核" });
    });
    await waitFor(() => {
      expect(screen.getByLabelText("你的回答")).toHaveValue("我负责过核");
    });

    // the candidate types between existing words while ASR keeps streaming
    fireEvent.change(screen.getByLabelText("你的回答"), { target: { value: "我负责过（核心）核" } });
    act(() => {
      useTranscriptStore.getState().applyEvent({ kind: "replace", text: "我负责过核心系统" });
    });

    // span was edited inside -> the box must NOT be duplicated; only the safe branch is allowed:
    // either untouched or a clean span replace. Never a cumulative append of the whole text.
    await waitFor(() => {
      const value = (screen.getByLabelText("你的回答") as HTMLTextAreaElement).value;
      expect(value).not.toContain("核我负责");
      expect(value.length).toBeLessThanOrEqual("我负责过（核心）核心系统".length + 4);
    });
  });
});

describe("question playback", () => {
  it("synthesizes the question once", async () => {
    const client = fakeClient();
    renderRoom(client);
    await screen.findByText("讲讲你最有挑战的项目");

    fireEvent.click(screen.getByRole("button", { name: "朗读题目" }));

    await waitFor(() => {
      expect(client.synthesizeSpeech).toHaveBeenCalledWith({
        text: "讲讲你最有挑战的项目",
        voice: null,
      });
    });
    await waitFor(() => {
      expect(client.fetchTtsAudio).toHaveBeenCalledWith("/api/v1/media/tts/abc.mp3");
    });
  });
});
