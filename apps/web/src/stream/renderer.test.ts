import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { createStreamRenderer } from "./renderer";

describe("createStreamRenderer", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("smooths a 500-char burst into many small frames", () => {
    const frames: string[] = [];
    const renderer = createStreamRenderer({
      onContent: (text) => frames.push(text),
      intervalMs: 40,
      charsPerTick: 12,
    });

    renderer.push("content", "字".repeat(500));
    vi.runAllTimers();

    expect(frames.length).toBeGreaterThanOrEqual(40);
    expect(frames.join("")).toBe("字".repeat(500));
    expect(renderer.pending().content).toBe(0);
  });

  it("keeps content and reasoning independent", () => {
    const content: string[] = [];
    const reasoning: string[] = [];
    const renderer = createStreamRenderer({
      onContent: (text) => content.push(text),
      onReasoning: (text) => reasoning.push(text),
      charsPerTick: 2,
      intervalMs: 10,
    });

    renderer.push("reasoning", "先想");
    renderer.push("content", "答案");
    vi.runAllTimers();

    expect(reasoning.join("")).toBe("先想");
    expect(content.join("")).toBe("答案");
  });

  it("flushes the tail and emits done last", () => {
    const order: string[] = [];
    const renderer = createStreamRenderer({
      onContent: (text) => order.push(`content:${text}`),
      onDone: () => order.push("done"),
      charsPerTick: 1,
      intervalMs: 1000,
    });

    renderer.push("content", "abc");
    renderer.done();

    expect(order).toEqual(["content:abc", "done"]);
  });

  it("stops emitting after stop()", () => {
    const frames: string[] = [];
    const renderer = createStreamRenderer({ onContent: (text) => frames.push(text) });

    renderer.push("content", "不应该出现");
    renderer.stop();
    vi.runAllTimers();

    expect(frames).toEqual([]);
  });

  it("drops chunks that arrive for a stale request", () => {
    const frames: string[] = [];
    const stale = vi.fn();
    let active = true;
    const renderer = createStreamRenderer({
      onContent: (text) => frames.push(text),
      isActive: () => active,
      onStale: stale,
      intervalMs: 10,
      charsPerTick: 4,
    });

    active = false;
    renderer.push("content", "过期内容");
    vi.runAllTimers();

    expect(frames).toEqual([]);
    expect(stale).toHaveBeenCalled();
  });

  it("drops a buffered tail when the request turns stale mid-render", () => {
    const frames: string[] = [];
    let active = true;
    const renderer = createStreamRenderer({
      onContent: (text) => frames.push(text),
      isActive: () => active,
      intervalMs: 40,
      charsPerTick: 2,
    });

    renderer.push("content", "abcdef");
    vi.advanceTimersByTime(40); // one tick: "ab"
    active = false;
    vi.runAllTimers();

    expect(frames.join("")).toBe("ab");
    expect(renderer.pending().content).toBe(0);
  });
});
