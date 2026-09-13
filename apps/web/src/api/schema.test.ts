import { describe, expect, it } from "vitest";

import type { paths } from "./schema";

type ChatSession =
  paths["/api/v1/chat/sessions"]["get"]["responses"][200]["content"]["application/json"][number];

type ChatMessage =
  paths["/api/v1/chat/sessions/{session_id}/messages"]["get"]["responses"][200]["content"]["application/json"][number];

type ModelView =
  paths["/api/v1/models"]["get"]["responses"][200]["content"]["application/json"][number];

describe("generated API types", () => {
  it("describe the chat session contract", () => {
    const session: ChatSession = {
      id: "s1",
      kind: "chat",
      title: "会话",
      model_ref: null,
      message_count: 0,
      created_at: "2026-09-13T00:00:00Z",
      updated_at: "2026-09-13T00:00:00Z",
    };

    expect(Object.keys(session)).toContain("message_count");
    expect(session.model_ref).toBeNull();
  });

  it("describe message bookkeeping fields used by history replay", () => {
    const message: ChatMessage = {
      id: "m1",
      seq: 1,
      role: "assistant",
      content: "答案",
      reasoning: "推理",
      token_count: 12,
      error_message: null,
      created_at: "2026-09-13T00:00:00Z",
    };

    expect(message.seq).toBe(1);
    expect(message.reasoning).toBe("推理");
  });

  it("expose the model registry projection without credentials", () => {
    const models: ModelView[] = [
      {
        name: "deepseek-flash",
        model_id: "deepseek-flash",
        provider: "deepseek",
        supports_reasoning: true,
        configured: false,
        is_default: true,
      },
    ];

    expect(models[0]?.configured).toBe(false);
    expect(models[0]).not.toHaveProperty("api_key");
  });

  it("include the SSE endpoint path", () => {
    const path: keyof paths = "/api/v1/chat/sessions/{session_id}/stream";

    expect(path).toContain("/stream");
  });
});
