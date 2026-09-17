/**
 * P28 second layer: the chat Composer keeps its OWN box state and merged transcripts with
 * the batch-era rule — realtime partials arriving one after another re-appended the whole
 * cumulative text (the "我好好，我是来好，我是来自…" signature users hit in the browser).
 * These tests drive the real component through a growing/correcting transcript sequence.
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Composer } from "./Composer";

function box() {
  return screen.getByLabelText("输入消息") as HTMLTextAreaElement;
}

describe("chat composer realtime transcript (P28 layer 2)", () => {
  it("growing/correcting partials replace the span instead of accumulating", () => {
    const view = render(<Composer onSend={vi.fn()} onCancel={vi.fn()} streaming={false} transcript="我" />);
    expect(box().value).toBe("我");

    for (const next of ["好好，我是来", "好，我是来自", "好，我是来自于。"]) {
      view.rerender(
        <Composer onSend={vi.fn()} onCancel={vi.fn()} streaming={false} transcript={next} />,
      );
      expect(box().value).toBe(next);
    }
  });

  it("keeps handwriting when the vendor corrects the transcript span", () => {
    const view = render(<Composer onSend={vi.fn()} onCancel={vi.fn()} streaming={false} transcript="你好" />);
    fireEvent.change(box(), { target: { value: "你好abc" } });
    view.rerender(<Composer onSend={vi.fn()} onCancel={vi.fn()} streaming={false} transcript="你好世界" />);
    expect(box().value).toBe("你好世界abc");
  });

  it("a new session after submit starts a fresh span", () => {
    const onSend = vi.fn();
    const view = render(<Composer onSend={onSend} onCancel={vi.fn()} streaming={false} transcript="第一句。" />);
    fireEvent.click(screen.getByRole("button", { name: /发送/ }));
    expect(onSend).toHaveBeenCalledWith("第一句。");
    expect(box().value).toBe("");

    view.rerender(<Composer onSend={onSend} onCancel={vi.fn()} streaming={false} transcript="第二句" />);
    expect(box().value).toBe("第二句");
    view.rerender(<Composer onSend={onSend} onCancel={vi.fn()} streaming={false} transcript="第二句开始" />);
    expect(box().value).toBe("第二句开始");
  });
});
