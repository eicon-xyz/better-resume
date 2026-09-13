import { describe, expect, it, vi } from "vitest";

import { createApiClient, type UploadOptions } from "./client";
import { ApiError } from "./errors";
import type { QuestionBatchView } from "./types";

class FakeXhr {
  upload: { onprogress: ((event: ProgressEvent) => void) | null } = { onprogress: null };
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  ontimeout: (() => void) | null = null;
  onabort: (() => void) | null = null;
  status = 201;
  responseText = "{}";
  withCredentials = false;
  timeout = 0;
  responseType = "";
  method = "";
  url = "";
  body: FormData | null = null;

  open(method: string, url: string) {
    this.method = method;
    this.url = url;
  }

  send(body: FormData) {
    this.body = body;
  }

  abort() {
    this.onabort?.();
  }

  emitProgress(loaded: number, total: number) {
    this.upload.onprogress?.({
      lengthComputable: true,
      loaded,
      total,
    } as ProgressEvent);
  }

  finish() {
    this.onload?.();
  }
}

const BATCH = {
  session: {
    id: "s-1",
    status: "ready",
    interview_type: null,
    question_count: 2,
    resume_score: 70,
    created_at: "2026-09-13T00:00:00Z",
    updated_at: "2026-09-13T00:00:00Z",
  },
  questions: [
    { question_no: "1", topic_no: 1, follow_up_index: 0, kind: "main", text: "第 1 题", focus_points: ["F1"] },
    { question_no: "2", topic_no: 2, follow_up_index: 0, kind: "main", text: "第 2 题", focus_points: ["F2"] },
  ],
  suggestions: ["补充量化"],
  flow: { status: "asking", current_question_no: "1", total_questions: 2, follow_up_count: 0, max_follow_up: 2 },
  replayed: false,
} satisfies QuestionBatchView;

function uploadWithFake(xhr: FakeXhr, options: UploadOptions = {}) {
  const client = createApiClient({});
  const file = new File(["%PDF-1.4 resume"], "cv.pdf", { type: "application/pdf" });
  return client.uploadResumeAndGenerateQuestions("s-1", file, {
    xhrFactory: () => xhr as unknown as XMLHttpRequest,
    ...options,
  });
}

describe("interview endpoints", () => {
  it("creates a session with JSON", async () => {
    const fetchImpl = vi.fn(() =>
      Promise.resolve(new Response(JSON.stringify({ id: "s-1", status: "draft" }), { status: 201 })),
    );
    const client = createApiClient({ fetchImpl: fetchImpl as unknown as typeof fetch });

    const session = await client.createInterviewSession({});

    expect(session.id).toBe("s-1");
    expect(fetchImpl).toHaveBeenCalledWith(
      "/api/v1/interview/sessions",
      expect.objectContaining({ method: "POST", credentials: "include" }),
    );
  });

  it("submits an answer and returns the next question", async () => {
    const fetchImpl = vi.fn(() =>
      Promise.resolve(
        new Response(
          JSON.stringify({
            session: BATCH.session,
            answer: { question_no: "1", score: 80 },
            flow: BATCH.flow,
            next_action: "next_question",
            next_question_no: "2",
            next_question: BATCH.questions[1],
            replayed: false,
          }),
          { status: 201 },
        ),
      ),
    );
    const client = createApiClient({ fetchImpl: fetchImpl as unknown as typeof fetch });

    const result = await client.submitInterviewAnswer("s-1", {
      question_no: "1",
      answer: "我的回答",
      request_id: "r-1",
    });

    expect(result.next_action).toBe("next_question");
    expect(result.next_question?.text).toBe("第 2 题");
  });

  it("restores, finishes and reads the report", async () => {
    const fetchImpl = vi.fn((url: string) => {
      const body = url.endsWith("/restore")
        ? { session: BATCH.session, flow: BATCH.flow }
        : { session: BATCH.session, overall_score: 77 };
      return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
    });
    const client = createApiClient({ fetchImpl: fetchImpl as unknown as typeof fetch });

    await expect(client.restoreInterview("s-1")).resolves.toBeTruthy();
    await expect(client.finishInterview("s-1")).resolves.toMatchObject({ overall_score: 77 });
    await expect(client.getInterviewReport("s-1")).resolves.toMatchObject({ overall_score: 77 });
  });
});

describe("uploadResumeAndGenerateQuestions", () => {
  it("posts multipart form data with progress reporting", async () => {
    const xhr = new FakeXhr();
    xhr.status = 201;
    xhr.responseText = JSON.stringify(BATCH);
    const progress: number[] = [];

    const promise = uploadWithFake(xhr, { onProgress: (ratio) => progress.push(ratio) });

    expect(xhr.method).toBe("POST");
    expect(xhr.url).toBe("/api/v1/interview/sessions/s-1/questions");
    expect(xhr.withCredentials).toBe(true);
    expect(xhr.body?.get("file")).toBeInstanceOf(File);

    xhr.emitProgress(5, 10);
    xhr.emitProgress(10, 10);
    xhr.finish();

    const result: QuestionBatchView = await promise;
    expect(result.questions).toHaveLength(2);
    expect(progress).toEqual([0.5, 1]);
  });

  it("maps a 400 parse error into an ApiError with the backend detail", async () => {
    const xhr = new FakeXhr();
    xhr.status = 400;
    xhr.responseText = JSON.stringify({ detail: "PDF 没有可提取的文本层", code: "text_layer_missing" });

    const promise = uploadWithFake(xhr);
    xhr.finish();

    await expect(promise).rejects.toMatchObject({
      name: "ApiError",
      kind: "invalid",
      status: 400,
      message: "PDF 没有可提取的文本层",
    });
  });

  it("maps a 503 into a server error", async () => {
    const xhr = new FakeXhr();
    xhr.status = 503;
    xhr.responseText = JSON.stringify({ detail: "environment variable X is not set" });

    const promise = uploadWithFake(xhr);
    xhr.finish();

    await expect(promise).rejects.toBeInstanceOf(ApiError);
  });

  it("reports aborts and timeouts distinctly", async () => {
    const controller = new AbortController();
    const aborted = new FakeXhr();
    const abortPromise = uploadWithFake(aborted, { signal: controller.signal });
    controller.abort();
    await expect(abortPromise).rejects.toMatchObject({ kind: "aborted" });

    const timedOut = new FakeXhr();
    const timeoutPromise = uploadWithFake(timedOut);
    timedOut.ontimeout?.();
    await expect(timeoutPromise).rejects.toMatchObject({ kind: "timeout" });

    const failed = new FakeXhr();
    const networkPromise = uploadWithFake(failed);
    failed.onerror?.();
    await expect(networkPromise).rejects.toMatchObject({ kind: "network" });
  });
});
