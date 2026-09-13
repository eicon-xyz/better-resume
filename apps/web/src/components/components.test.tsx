import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Button, Card, Collapsible, Empty, Spinner, Textarea } from ".";

describe("Button", () => {
  it("renders its label and handles clicks", async () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>发送</Button>);

    await userEvent.click(screen.getByRole("button", { name: "发送" }));

    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("blocks interaction while loading", () => {
    const onClick = vi.fn();
    render(
      <Button loading onClick={onClick}>
        发送
      </Button>,
    );

    const button = screen.getByRole("button", { name: "发送" });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "true");
  });
});

describe("Textarea", () => {
  it("forwards value and change events", async () => {
    const onChange = vi.fn();
    render(<Textarea placeholder="输入问题" onChange={onChange} />);

    await userEvent.type(screen.getByPlaceholderText("输入问题"), "你好");

    expect(onChange).toHaveBeenCalled();
  });
});

describe("Card", () => {
  it("renders an optional heading and children", () => {
    render(
      <Card title="会话">
        <p>内容</p>
      </Card>,
    );

    expect(screen.getByRole("heading", { name: "会话" })).toBeInTheDocument();
    expect(screen.getByText("内容")).toBeInTheDocument();
  });
});

describe("Spinner", () => {
  it("announces itself as a status", () => {
    render(<Spinner label="生成中" />);

    expect(screen.getByRole("status", { name: "生成中" })).toBeInTheDocument();
  });
});

describe("Collapsible", () => {
  it("hides content until opened and reports toggles", async () => {
    const onToggle = vi.fn();
    const { rerender } = render(
      <Collapsible label="深度思考" open={false} onToggle={onToggle}>
        <span>推理内容</span>
      </Collapsible>,
    );

    expect(screen.queryByText("推理内容")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /深度思考/ }));
    expect(onToggle).toHaveBeenCalledWith(true);

    rerender(
      <Collapsible label="深度思考" open onToggle={onToggle}>
        <span>推理内容</span>
      </Collapsible>,
    );
    expect(screen.getByRole("region", { name: "深度思考" })).toHaveTextContent("推理内容");
    expect(screen.getByRole("button", { name: /深度思考/ })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
  });
});

describe("Empty", () => {
  it("shows title, description and action", () => {
    render(<Empty title="还没有会话" description="先问一个问题" action={<Button>新建</Button>} />);

    expect(screen.getByText("还没有会话")).toBeInTheDocument();
    expect(screen.getByText("先问一个问题")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "新建" })).toBeInTheDocument();
  });
});
