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

  it("keeps a second identical answer while history is still behind (P8 / web-04)", () => {
    // Two answers with the same text: the older draft is replayed by history, the newer one is
    // not there yet. Matching on content dropped the newer one too, so the reply the user just
    // watched appear vanished until the refetch landed (and stayed gone if it failed).
    const server = [
      view({ seq: 1, role: "user", content: "你好", client_message_id: "cm-1" }),
      view({ seq: 2, role: "assistant", content: "你好，我是助手" }),
    ];
    const localMessages = [
      local({ key: "cm-1", role: "user", content: "你好", clientMessageId: "cm-1" }),
      local({ key: "req-1", role: "assistant", content: "你好，我是助手" }),
      local({ key: "cm-2", role: "user", content: "你好", clientMessageId: "cm-2" }),
      local({ key: "req-2", role: "assistant", content: "你好，我是助手" }),
    ];

    const merged = mergeHistory(server, localMessages);

    expect(merged.map((message) => message.key)).toEqual(["cm-1", "server:2", "cm-2", "req-2"]);
  });

  it("drops both copies once history has caught up", () => {
    const server = [
      view({ seq: 1, role: "user", content: "你好", client_message_id: "cm-1" }),
      view({ seq: 2, role: "assistant", content: "你好，我是助手" }),
      view({ seq: 3, role: "user", content: "你好", client_message_id: "cm-2" }),
      view({ seq: 4, role: "assistant", content: "你好，我是助手" }),
    ];
    const localMessages = [
      local({ key: "cm-1", role: "user", content: "你好", clientMessageId: "cm-1" }),
      local({ key: "req-1", role: "assistant", content: "你好，我是助手" }),
      local({ key: "cm-2", role: "user", content: "你好", clientMessageId: "cm-2" }),
      local({ key: "req-2", role: "assistant", content: "你好，我是助手" }),
    ];

    const merged = mergeHistory(server, localMessages);

    expect(merged.map((message) => message.key)).toEqual([
      "cm-1",
      "server:2",
      "cm-2",
      "server:4",
    ]);
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
