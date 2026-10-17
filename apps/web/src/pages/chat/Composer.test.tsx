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

describe("chat composer realtime transcript", () => {
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

describe("chat composer 卡片", () => {
  it("counts the characters from the box's own value", () => {
    render(<Composer onSend={vi.fn()} onCancel={vi.fn()} streaming={false} />);
    expect(screen.getByText("0 字")).toBeInTheDocument();

    fireEvent.change(box(), { target: { value: "我重构了写入链路" } });
    expect(screen.getByText("8 字")).toBeInTheDocument();

    fireEvent.change(box(), { target: { value: "   " } });
    expect(screen.getByText("0 字")).toBeInTheDocument();
  });

  it("keeps the send button disabled until there is text to send", () => {
    render(<Composer onSend={vi.fn()} onCancel={vi.fn()} streaming={false} />);
    expect(screen.getByRole("button", { name: "发送" })).toBeDisabled();

    fireEvent.change(box(), { target: { value: "你好" } });
    expect(screen.getByRole("button", { name: "发送" })).toBeEnabled();
  });

  it("shows the keyboard shortcut and the recording state on the voice button", () => {
    render(
      <Composer
        onSend={vi.fn()}
        onCancel={vi.fn()}
        streaming={false}
        recording
        onToggleRecording={vi.fn()}
      />,
    );

    expect(screen.getByText("Enter 发送，Shift+Enter 换行")).toBeInTheDocument();
    const mic = screen.getByRole("button", { name: "停止录音" });
    expect(mic).toHaveAttribute("aria-pressed", "true");
    expect(mic).toHaveAttribute("data-recording", "true");
  });
});
