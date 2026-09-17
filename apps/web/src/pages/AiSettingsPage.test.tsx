/** M5-T7: the AI settings panel — listing, switching, honest "not configured" state. */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { ApiProvider } from "../api/ApiContext";
import type { ApiClient } from "../api/client";
import { ApiError } from "../api/errors";
import type { SceneView } from "../api/types";
import { AiSettingsPage } from "./AiSettingsPage";

function scene(overrides: Partial<SceneView> = {}): SceneView {
  return {
    scene: "chat",
    label: "对话",
    adapter: "openai_compat",
    target_ref: "deepseek-flash",
    configured: true,
    is_default: true,
    ...overrides,
  } as SceneView;
}

const SCENES: SceneView[] = [
  scene(),
  scene({
    scene: "question_extraction",
    label: "出题",
    adapter: "xingyun",
    target_ref: "flow-q",
    configured: false,
    is_default: false,
  }),
  scene({ scene: "answer_evaluation", label: "答案评分", is_default: false }),
  scene({ scene: "follow_up", label: "追问", is_default: false }),
  scene({ scene: "report_summary", label: "报告总结", is_default: false }),
];

function fakeClient(overrides: Partial<ApiClient> = {}): ApiClient {
  return {
    listScenes: vi.fn(async () => SCENES),
    updateScene: vi.fn(async (name: string, body: { adapter: string; target_ref: string }) => ({
      ...scene({ scene: name, is_default: false }),
      adapter: body.adapter,
      target_ref: body.target_ref,
    })),
    ...overrides,
  } as unknown as ApiClient;
}

function renderPage(client: ApiClient) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ApiProvider client={client}>
        <MemoryRouter initialEntries={["/settings/ai"]}>
          <Routes>
            <Route path="/settings/ai" element={<AiSettingsPage />} />
            <Route path="/chat" element={<p>对话页</p>} />
          </Routes>
        </MemoryRouter>
      </ApiProvider>
    </QueryClientProvider>,
  );
}

describe("AiSettingsPage", () => {
  it("lists every scene with its label, technical name and binding", async () => {
    renderPage(fakeClient());

    expect(await screen.findByText("对话")).toBeInTheDocument();
    expect(screen.getByText("question_extraction")).toBeInTheDocument();
    expect(screen.getByText("报告总结")).toBeInTheDocument();
    expect(screen.getAllByRole("row")).toHaveLength(6); // header + five scenes
  });

  it("marks unconfigured scenes and names the missing variables", async () => {
    renderPage(fakeClient());

    const missing = await screen.findByText(/未配置/);
    expect(missing).toHaveTextContent("XINGCHEN_API_KEY");
  });

  it("offers the Model Studio application kind for every scene", async () => {
    renderPage(fakeClient());

    const select = (await screen.findByLabelText("对话 供应商")) as HTMLSelectElement;

    expect(Array.from(select.options).map((option) => option.value)).toEqual([
      "openai_compat",
      "xingyun",
      "dashscope_app",
    ]);
  });

  it("names BR_DASHSCOPE_API_KEY for an unconfigured application binding", async () => {
    const client = fakeClient({
      listScenes: vi.fn(async () => [
        scene({
          adapter: "dashscope_app",
          target_ref: "app-1",
          configured: false,
          is_default: false,
        }),
      ]),
    });
    renderPage(client);

    const missing = await screen.findByText(/未配置/);
    expect(missing).toHaveTextContent("BR_DASHSCOPE_API_KEY");
  });

  it("switches a scene and sends the new binding", async () => {
    const client = fakeClient();
    renderPage(client);
    await screen.findByText("答案评分");

    fireEvent.change(screen.getByLabelText("答案评分 供应商"), { target: { value: "xingyun" } });
    fireEvent.change(screen.getByLabelText("答案评分 目标"), { target: { value: "flow-eval" } });
    fireEvent.click(screen.getAllByRole("button", { name: "保存" })[2]!);

    await waitFor(() => {
      expect(client.updateScene).toHaveBeenCalledWith("answer_evaluation", {
        adapter: "xingyun",
        target_ref: "flow-eval",
      });
    });
  });

  it("explains a rejected switch with the shared error copy", async () => {
    const client = fakeClient({
      updateScene: vi.fn(async () => {
        throw new ApiError("rate limit exceeded for general", {
          kind: "rate_limited",
          status: 429,
          retryAfterSeconds: 2,
        });
      }),
    });
    renderPage(client);
    await screen.findByText("答案评分");

    fireEvent.change(screen.getByLabelText("答案评分 目标"), { target: { value: "flow-x" } });
    fireEvent.click(screen.getAllByRole("button", { name: "保存" })[2]!);

    expect(await screen.findByRole("alert")).toHaveTextContent("服务繁忙，请 2 秒后重试");
  });

  it("tells an unauthenticated visitor to log in first", async () => {
    const client = fakeClient({
      listScenes: vi.fn(async () => {
        throw new ApiError("not authenticated", { kind: "unauthorized", status: 401 });
      }),
    });
    renderPage(client);

    expect(await screen.findByRole("alert")).toHaveTextContent("登录已过期");
  });

  it("keeps save disabled until a row actually changes", async () => {
    const client = fakeClient();
    renderPage(client);
    await screen.findByText("对话");

    const saveButtons = screen.getAllByRole("button", { name: "保存" });
    expect(saveButtons.every((button) => (button as HTMLButtonElement).disabled)).toBe(true);

    fireEvent.change(screen.getByLabelText("对话 目标"), { target: { value: "deepseek-v4-pro" } });
    expect(screen.getAllByRole("button", { name: "保存" })[0]).not.toBeDisabled();
  });
});
