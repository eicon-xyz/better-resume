import { describe, expect, it } from "vitest";

import type { ChatMessageView } from "../api/types";
import { mergeHistory, toLocalMessage } from "./selectors";
import type { ChatMessage } from "./store";

function view(partial: Partial<ChatMessageView> & { seq: number; role: string }): ChatMessageView {
  return {
    id: `m-${partial.seq}`,
    seq: partial.seq,
    role: partial.role,
    content: partial.content ?? "",
    reasoning: partial.reasoning ?? null,
    client_message_id: partial.client_message_id ?? null,
    token_count: partial.token_count ?? null,
    error_message: partial.error_message ?? null,
    created_at: "2026-09-13T00:00:00Z",
  };
}

function local(partial: Partial<ChatMessage> & { key: string; role: "user" | "assistant" }): ChatMessage {
  return {
    content: "",
    reasoning: "",
    streaming: false,
    error: null,
    clientMessageId: null,
    seq: null,
    ...partial,
  };
}

describe("toLocalMessage", () => {
  it("prefers the client message id as the local key", () => {
    expect(toLocalMessage(view({ seq: 1, role: "user", client_message_id: "cm-1" })).key).toBe("cm-1");
    expect(toLocalMessage(view({ seq: 1, role: "user" })).key).toBe("server:1");
  });
});

describe("mergeHistory", () => {
  it("drops optimistic user turns that are already persisted", () => {
    const server = [view({ seq: 1, role: "user", content: "你好", client_message_id: "cm-1" })];
    const localMessages = [
      local({ key: "cm-1", role: "user", content: "你好", clientMessageId: "cm-1" }),
    ];

    const merged = mergeHistory(server, localMessages);

    expect(merged).toHaveLength(1);
    expect(merged[0]?.seq).toBe(1);
  });

  it("keeps an in-flight draft and drops an already replayed one", () => {
    const server = [view({ seq: 2, role: "assistant", content: "旧答案" })];
    const localMessages = [
      local({ key: "req-done", role: "assistant", content: "旧答案" }),
      local({ key: "req-live", role: "assistant", content: "正在写", streaming: true }),
    ];

    const merged = mergeHistory(server, localMessages);

    expect(merged.map((message) => message.key)).toEqual(["server:2", "req-live"]);
  });

  it("keeps a not-yet-persisted user turn at the end", () => {
    const server = [view({ seq: 1, role: "user", content: "第一问", client_message_id: "cm-1" })];
    const localMessages = [
      local({ key: "cm-1", role: "user", content: "第一问", clientMessageId: "cm-1" }),
      local({ key: "cm-2", role: "user", content: "第二问", clientMessageId: "cm-2" }),
    ];

    const merged = mergeHistory(server, localMessages);

    expect(merged.map((message) => message.content)).toEqual(["第一问", "第二问"]);
  });
});
