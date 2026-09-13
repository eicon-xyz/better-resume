import { beforeEach, describe, expect, it } from "vitest";

import { useChatStore } from "./store";

describe("chat store", () => {
  beforeEach(() => {
    useChatStore.getState().reset();
  });

  it("keeps content and reasoning on separate channels", () => {
    const store = useChatStore.getState();
    store.appendUser({ clientMessageId: "cm-1", content: "你好" });
    store.startAssistant("req-1");
    store.appendReasoning("req-1", "先想");
    store.appendContent("req-1", "你");
    store.appendContent("req-1", "好");
    store.finishAssistant("req-1");

    const state = useChatStore.getState();
    expect(state.messages.map((message) => message.role)).toEqual(["user", "assistant"]);
    expect(state.messages[0]).toMatchObject({ content: "你好", clientMessageId: "cm-1" });
    expect(state.messages[1]).toMatchObject({ content: "你好", reasoning: "先想", streaming: false });
    expect(state.streaming).toBe(false);
    expect(state.activeRequestId).toBeNull();
  });

  it("ignores chunks for a request that is no longer active", () => {
    const store = useChatStore.getState();
    store.startAssistant("req-1");
    store.finishAssistant("req-1");
    store.appendContent("req-1", "迟到");

    expect(useChatStore.getState().messages[0]?.content).toBe("");
  });

  it("records the failure on the assistant message", () => {
    const store = useChatStore.getState();
    store.startAssistant("req-1");
    store.appendContent("req-1", "半句");
    store.finishAssistant("req-1", "上游超时");

    expect(useChatStore.getState().messages[0]).toMatchObject({
      content: "半句",
      error: "上游超时",
      streaming: false,
    });
    expect(useChatStore.getState().error).toBe("上游超时");
  });

  it("opening another session clears run state", () => {
    const store = useChatStore.getState();
    store.appendUser({ clientMessageId: "cm-1", content: "旧会话" });
    store.openSession("s-2");

    expect(useChatStore.getState().messages).toEqual([]);
    expect(useChatStore.getState().sessionId).toBe("s-2");
  });
});
