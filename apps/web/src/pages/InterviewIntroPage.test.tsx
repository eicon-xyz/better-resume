import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiProvider } from "../api/ApiContext";
import type { ApiClient, UploadOptions } from "../api/client";
import { ApiError } from "../api/errors";
import { useChatStore } from "../chat/store";
import { InterviewIntroPage } from "./InterviewIntroPage";

const BATCH = {
  session: {
    id: "s-new",
    status: "ready",
    interview_type: null,
    question_count: 2,
    resume_score: 66,
    created_at: "2026-09-13T00:00:00Z",
    updated_at: "2026-09-13T00:00:00Z",
  },
  questions: [
    { question_no: "1", topic_no: 1, follow_up_index: 0, kind: "main", text: "讲讲你的项目", focus_points: ["取舍"] },
    { question_no: "2", topic_no: 2, follow_up_index: 0, kind: "main", text: "如何做压测", focus_points: ["指标"] },
  ],
  suggestions: ["补充量化结果"],
  flow: { status: "asking", current_question_no: "1", total_questions: 2, follow_up_count: 0, max_follow_up: 2 },
  replayed: false,
};

function fakeClient(overrides: Partial<ApiClient> = {}) {
  const client = {
    currentPrincipal: vi.fn(() => Promise.resolve({ user_id: "u1", roles: [] })),
    listInterviewSessions: vi.fn(() => Promise.resolve([])),
    createInterviewSession: vi.fn(() => Promise.resolve({ ...BATCH.session, id: "s-new", status: "draft" })),
    uploadResumeAndGenerateQuestions: vi.fn(() => Promise.resolve(BATCH)),
    restoreInterview: vi.fn(() => Promise.resolve({ session: BATCH.session, flow: BATCH.flow })),
    listModels: vi.fn(() => Promise.resolve([])),
    ...overrides,
  } as unknown as ApiClient;
  return client;
}

function renderPage(client: ApiClient) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ApiProvider client={client}>
        <MemoryRouter initialEntries={["/interview"]}>
          <Routes>
            <Route path="/interview" element={<InterviewIntroPage />} />
            <Route path="/interview/room/:sessionId" element={<p>房间已打开</p>} />
          </Routes>
        </MemoryRouter>
      </ApiProvider>
    </QueryClientProvider>,
  );
}

function pdfFile(name = "cv.pdf", content = "%PDF-1.7 简历内容", type = "application/pdf") {
  return new File([content], name, { type });
}

function selectFile(file: File): void {
  const input = screen.getByLabelText("选择简历 PDF");
  fireEvent.change(input, { target: { files: [file] } });
}

/** 创建表单默认收起，页面顶部与空态各有一个「创建模拟面试」入口；顶部入口在 DOM 里靠前。 */
async function openCreateForm(): Promise<void> {
  const createButtons = await screen.findAllByRole("button", { name: "创建模拟面试" });
  fireEvent.click(createButtons[0] as HTMLElement);
  await screen.findByRole("heading", { name: "第一步：上传简历" });
}

describe("InterviewIntroPage", () => {
  beforeEach(() => {
    useChatStore.getState().reset();
  });

  it("shows the dev login gate when unauthenticated", async () => {
    const client = fakeClient({
      currentPrincipal: vi.fn(() => Promise.reject(new Error("401"))),
    });

    renderPage(client);

    expect(await screen.findByRole("button", { name: "进入" })).toBeInTheDocument();
  });

  it("renders the upload card and the empty continue state", async () => {
    renderPage(fakeClient());

    await openCreateForm();
    expect(screen.getByRole("heading", { name: "第一步：上传简历" })).toBeInTheDocument();
    expect(screen.getByText("没有进行中的面试")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "开始面试" })).toBeDisabled();
  });

  it("rejects a file that is not a pdf", async () => {
    renderPage(fakeClient());

    await openCreateForm();
    selectFile(new File(["hello"], "notes.txt", { type: "text/plain" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("只支持 PDF 文件");
  });

  it("rejects a pdf without the magic header", async () => {
    renderPage(fakeClient());

    await openCreateForm();
    selectFile(pdfFile("fake.pdf", "MZ not really a pdf"));

    expect(await screen.findByRole("alert")).toHaveTextContent("不是有效的 PDF");
  });

  it("rejects an oversized pdf", async () => {
    renderPage(fakeClient());

    await openCreateForm();
    const huge = new File(["%PDF-" + "0".repeat(10 * 1024 * 1024)], "huge.pdf", {
      type: "application/pdf",
    });
    selectFile(huge);

    expect(await screen.findByRole("alert")).toHaveTextContent("文件过大");
  });

  it("creates a session, uploads the resume and navigates into the room", async () => {
    const client = fakeClient();
    renderPage(client);

    await openCreateForm();
    selectFile(pdfFile());

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "开始面试" })).toBeEnabled();
    });
    fireEvent.click(screen.getByRole("button", { name: "开始面试" }));

    expect(await screen.findByText("房间已打开")).toBeInTheDocument();
    expect(vi.mocked(client.createInterviewSession)).toHaveBeenCalledTimes(1);
    const [uploadedSession, uploadedFile, uploadOptions] =
      vi.mocked(client.uploadResumeAndGenerateQuestions).mock.calls[0] ?? [];

    expect(uploadedSession).toBe("s-new");
    expect(uploadedFile).toBeInstanceOf(File);
    expect(typeof uploadOptions?.onProgress).toBe("function");
  });

  it("keeps the chosen focus in controlled state and explains each option", async () => {
    renderPage(fakeClient());

    await openCreateForm();
    const select = screen.getByLabelText("面试侧重");
    fireEvent.change(select, { target: { value: "project" } });

    expect(select).toHaveValue("project");
    expect(screen.getByRole("option", { name: /项目深挖/ })).toHaveTextContent(
      "围绕项目经历追问技术取舍",
    );
  });

  it("drives the progress bar and its percentage from the upload progress", async () => {
    let reportProgress: ((ratio: number) => void) | undefined;
    const client = fakeClient({
      uploadResumeAndGenerateQuestions: vi.fn(
        (_sessionId: string, _file: File, options?: UploadOptions) => {
          reportProgress = options?.onProgress;
          return new Promise<never>(() => undefined);
        },
      ),
    });
    renderPage(client);

    await openCreateForm();
    selectFile(pdfFile());
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "开始面试" })).toBeEnabled();
    });
    fireEvent.click(screen.getByRole("button", { name: "开始面试" }));
    await waitFor(() => {
      expect(reportProgress).toBeTypeOf("function");
    });

    await act(async () => {
      reportProgress?.(0.42);
    });

    const bar = screen.getByRole("progressbar", { name: "上传进度" });
    expect(bar).toHaveAttribute("aria-valuenow", "42");
    expect((bar.lastElementChild as HTMLElement).style.width).toBe("42%");
    expect(bar.parentElement).toHaveTextContent("正在生成题目…");
  });

  it("sends the chosen interview focus when creating the session", async () => {
    const client = fakeClient();
    renderPage(client);

    await openCreateForm();
    fireEvent.change(screen.getByLabelText("面试侧重"), { target: { value: "project" } });
    selectFile(pdfFile());
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "开始面试" })).toBeEnabled();
    });
    fireEvent.click(screen.getByRole("button", { name: "开始面试" }));

    await screen.findByText("房间已打开");
    expect(vi.mocked(client.createInterviewSession)).toHaveBeenCalledWith({
      interview_type: "project",
    });
  });

  it("surfaces a backend parse failure", async () => {
    const client = fakeClient({
      // The real client always rejects with ApiError; the hook must surface its message.
      uploadResumeAndGenerateQuestions: vi.fn(() =>
        Promise.reject(
          new ApiError("PDF 没有可提取的文本层", { kind: "invalid", status: 400 }),
        ),
      ),
    });
    renderPage(client);

    await openCreateForm();
    selectFile(pdfFile());
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "开始面试" })).toBeEnabled();
    });
    fireEvent.click(screen.getByRole("button", { name: "开始面试" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("PDF 没有可提取的文本层");
    expect(screen.queryByText("房间已打开")).not.toBeInTheDocument();
  });

  it("accepts a dropped pdf through the same validation path", async () => {
    renderPage(fakeClient());

    await openCreateForm();
    const dropzone = screen.getByLabelText("选择简历 PDF").closest("label");
    expect(dropzone).not.toBeNull();
    fireEvent.drop(dropzone as HTMLElement, { dataTransfer: { files: [pdfFile()] } });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "开始面试" })).toBeEnabled();
    });
  });

  it("continues an unfinished interview through restore", async () => {
    const client = fakeClient({
      listInterviewSessions: vi.fn(() =>
        Promise.resolve([
          {
            id: "s-old",
            status: "in_progress",
            interview_type: "backend",
            question_count: 5,
            resume_score: 70,
            created_at: "2026-09-13T00:00:00Z",
            updated_at: "2026-09-13T00:00:00Z",
          },
        ]),
      ),
    });
    renderPage(client);

    const continueButton = await screen.findByRole("button", { name: "继续" });
    fireEvent.click(continueButton);

    expect(await screen.findByText("房间已打开")).toBeInTheDocument();
    expect(client.restoreInterview).toHaveBeenCalledWith("s-old");
  });

  it("starts on the empty state and expands the create form from the header button", async () => {
    renderPage(fakeClient());

    const createButtons = await screen.findAllByRole("button", { name: "创建模拟面试" });
    expect(createButtons).toHaveLength(2);
    expect(screen.queryByRole("heading", { name: "第一步：上传简历" })).not.toBeInTheDocument();

    fireEvent.click(createButtons[0] as HTMLElement);

    expect(await screen.findByRole("heading", { name: "第一步：上传简历" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "创建模拟面试" })).toBeInTheDocument();
    expect(screen.queryByText("创建你的第一场模拟面试，开始结构化练习")).not.toBeInTheDocument();
  });

  it("expands the create form from the empty-state button", async () => {
    renderPage(fakeClient());

    const createButtons = await screen.findAllByRole("button", { name: "创建模拟面试" });
    fireEvent.click(createButtons[createButtons.length - 1] as HTMLElement);

    expect(await screen.findByRole("heading", { name: "第一步：上传简历" })).toBeInTheDocument();
  });

  it("shows the quota subtitle and the three-step guide in the empty state", async () => {
    renderPage(fakeClient());

    expect(await screen.findByText("免费额度：2 场")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "模拟面试" })).toBeInTheDocument();
    expect(screen.getByText("创建你的第一场模拟面试，开始结构化练习")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "1. 选择简历" })).toBeInTheDocument();
    expect(screen.getByText("选择简历，填写岗位和可选 JD，生成一场专属模拟面试。")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "2. 开始模拟" })).toBeInTheDocument();
    expect(screen.getByText("系统准备面试计划与首题，随后进入实时语音逐轮答题。")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "3. 生成报告" })).toBeInTheDocument();
    expect(screen.getByText("完成模拟后生成专属面试报告，查看面试表现与改进建议。")).toBeInTheDocument();
  });
});
