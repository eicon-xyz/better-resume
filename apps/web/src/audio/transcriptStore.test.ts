import { beforeEach, describe, expect, it } from "vitest";

import {
  mergeTranscript,
  replaceTranscript,
  transcriptText,
  useTranscriptStore,
} from "./transcriptStore";

beforeEach(() => {
  useTranscriptStore.getState().reset();
});

describe("transcript store", () => {
  it("replaces the live area and keeps committed text", () => {
    const store = useTranscriptStore.getState();
    store.applyEvent({ kind: "archive", text: "第一句。" });
    store.applyEvent({ kind: "replace", text: "第二句" });

    const state = useTranscriptStore.getState();
    expect(state.committed).toBe("第一句。");
    expect(state.live).toBe("第二句");
    expect(transcriptText(state)).toBe("第一句。第二句");
  });

  it("clears the live area when a sentence is archived", () => {
    const store = useTranscriptStore.getState();
    store.applyEvent({ kind: "replace", text: "进行中" });
    store.applyEvent({ kind: "archive", text: "进行中。" });

    expect(useTranscriptStore.getState().live).toBe("");
    expect(useTranscriptStore.getState().committed).toBe("进行中。");
  });

  it("does not archive the same sentence twice", () => {
    const store = useTranscriptStore.getState();
    store.applyEvent({ kind: "archive", text: "重复。" });
    store.applyEvent({ kind: "archive", text: "重复。" });

    expect(useTranscriptStore.getState().committed).toBe("重复。");
  });

  it("treats final as the closing snapshot", () => {
    useTranscriptStore.getState().applyEvent({ kind: "final", text: "完整文本。" });

    const state = useTranscriptStore.getState();
    expect(state.committed).toBe("完整文本。");
    expect(state.live).toBe("");
    expect(state.status).toBe("closed");
  });
});

describe("mergeTranscript", () => {
  it("adopts the transcript when the box is empty or a prefix", () => {
    expect(mergeTranscript("", "你好世界")).toEqual({ text: "你好世界", notice: false });
    expect(mergeTranscript("你好", "你好世界")).toEqual({ text: "你好世界", notice: false });
  });

  it("appends a new utterance instead of dropping it (batch ASR presses)", () => {
    expect(mergeTranscript("第一句。", "第二句。")).toEqual({
      text: "第一句。第二句。",
      notice: true,
    });
  });

  it("never clobbers text the candidate typed", () => {
    expect(mergeTranscript("我负责了", "完全不同的话").text).toBe("我负责了完全不同的话");
    expect(mergeTranscript("手写", "转写").text).toContain("手写");
  });

  it("does not append the same run twice", () => {
    expect(mergeTranscript("你好世界", "你好世界")).toEqual({ text: "你好世界", notice: false });
    expect(mergeTranscript("你好世界！", "你好世界")).toEqual({
      text: "你好世界！",
      notice: false,
    });
  });

  it("does nothing when there is no transcript", () => {
    expect(mergeTranscript("手写内容", "")).toEqual({ text: "手写内容", notice: false });
  });
});

describe("replaceTranscript (P28: realtime partials replace their span, never re-append)", () => {
  it("replaces the contributed span while trailing handwriting stays put", () => {
    const r = replaceTranscript("你好我是测试", "你好我是", "你好我是来自重庆");
    expect(r).toEqual({ text: "你好我是来自重庆测试", notice: false });
  });

  it("replaces the span mid-text (user typed around it)", () => {
    const r = replaceTranscript("甲你好我是乙", "你好我是", "你好我是来自");
    expect(r).toEqual({ text: "甲你好我是来自乙", notice: false });
  });

  it("vendor correction (not an evolution) still replaces the span", () => {
    const r = replaceTranscript("第二句。街口响好", "第二句。街口响", "第二句接口响应");
    expect(r).toEqual({ text: "第二句接口响应好", notice: false });
  });

  it("first contribution of a session appends and flags a notice", () => {
    const r = replaceTranscript("好的", "", "你好我是");
    expect(r).toEqual({ text: "好的你好我是", notice: true });
  });

  it("first contribution already present in the box is a no-op", () => {
    expect(replaceTranscript("你好世界", "", "你好世界")).toEqual({
      text: "你好世界",
      notice: false,
    });
    expect(replaceTranscript("手写内容", "", "")).toEqual({ text: "手写内容", notice: false });
  });

  it("when the user edited INSIDE the span, the box is left untouched with a notice", () => {
    const r = replaceTranscript("你好我是重", "你好我是重庆", "你好我是重庆大学");
    expect(r).toEqual({ text: "你好我是重", notice: true });
  });

  it("rapid partials plus mid-stream typing never duplicate the transcript", () => {
    let value = "测";
    let previous = "";
    for (const next of ["你好", "你好我是", "你好我是来", "你好我是来自重庆"]) {
      const r = replaceTranscript(value, previous, next);
      value = r.text;
      previous = next;
      if (value === "测你好我是来") value += "（打字中）";
    }
    expect(value).toBe("测你好我是来自重庆（打字中）");
  });
});
