"""为部署冒烟提供一个确定性的 OpenAI 兼容端点。

compose 冒烟必须证明 nginx 会边产生边转发 SSE 帧，并升级 WebSocket。真实供应商会让这项检查
忽红忽绿并产生账单，所以冒烟把一条专用 smoke-fake 模型行指向本服务器（它只在 smoke compose
profile 下运行）。

首个内容分片刻意延迟：客户端因此应当在任何模型文本到达前先看到 API 自己的 ": ping" 心跳。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DEFAULT_CHUNKS = ("今天", "天气", "不错。")

#: 生成的问题必须携带的受控类别（D23）；在问题之间循环使用。
CATEGORY_VALUES = ("fundamentals", "project", "internship")

#: 携带此标记的提示要求无 category 形状，让 D23 规则回退继续经由同一个假上游被演练（Q2）。
#: 没有它时假上游会给出类别。
NO_CATEGORY_MARKER = "不给出 category"

#: 每个面试场景的非流式回答。api 不发 scene 头，所以假上游嗅探提示文本（每个阶段要的 JSON
#: 形状不同）。tests/test_fake_openai.py 读取真实 pydantic 契约，检查每个受控枚举字段都存在
#: 且合法；缺失或未知的值会让该守卫失败。
SCORE_PAYLOAD = {
    "score": 55.0,
    "feedback": "回答覆盖了主要流程，但缺少量化结果与失败复盘。",
    "missing_points": ["量化结果", "失败复盘"],
    "follow_up_needed": True,
}
FOLLOW_UP_PAYLOAD = {"text": "请补充一个具体的量化结果，说明改动前后的差异。"}
SUMMARY_PAYLOAD = {"summary": "整体结构清晰，深度尚可；建议用数据说明取舍与结果。"}


def scene_for(text: str) -> str:
    """这次补全由哪个阶段发起（嗅探提示，先看特征性标记）。"""
    # 按每个阶段要求的 JSON 形状匹配，而不是匹配零散词：评分提示也提到 追问
    # （follow_up_needed），出题提示则提到不含「总结」的措辞。
    if "道面试题" in text or "interview questions" in text or "questions[" in text:
        return "questions"
    if "{score, feedback" in text or "评分官" in text:
        return "score"
    if "{text}" in text or "提出一个具体的追问" in text:
        return "follow_up"
    if "{summary}" in text or "句总结" in text:
        return "summary"
    return "score"


def _question_payload(text: str) -> dict:
    match = re.search(r"请出 (\d+) 道面试题", text)
    count = int(match.group(1)) if match else 3
    count = max(1, min(count, 10))
    include_category = NO_CATEGORY_MARKER not in text
    questions = []
    for index in range(1, count + 1):
        question = {
            "topic": f"主题{index}",
            "focus_points": [f"要点{index}A", f"要点{index}B"],
            "text": f"第 {index} 题：请说明这个项目里你做过的一个具体取舍。",
        }
        if include_category:
            question["category"] = CATEGORY_VALUES[(index - 1) % len(CATEGORY_VALUES)]
        questions.append(question)
    return {
        "questions": questions,
        "resume_score": 72.0,
        "suggestions": ["补充量化结果"],
    }


def completion_payload(text: str) -> dict:
    scene = scene_for(text)
    if scene == "questions":
        return _question_payload(text)
    if scene == "follow_up":
        return dict(FOLLOW_UP_PAYLOAD)
    if scene == "summary":
        return dict(SUMMARY_PAYLOAD)
    return dict(SCORE_PAYLOAD)


class FakeOpenAI(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "fake-openai/1"

    first_delay = 2.0
    chunk_delay = 0.2
    chunks: tuple[str, ...] = DEFAULT_CHUNKS

    def log_message(self, fmt: str, *args: object) -> None:
        sys.stderr.write("fake-openai: " + (fmt % args) + "\n")

    def _json(self, payload: dict, *, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - 标准库钩子
        self._json({"object": "list", "data": [{"id": "smoke-fake", "object": "model"}]})

    def do_POST(self) -> None:  # noqa: N802 - 标准库钩子
        length = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._json({"error": "invalid json"}, status=400)
            return
        if not self.path.rstrip("/").endswith("/chat/completions"):
            self._json({"error": f"no route for {self.path}"}, status=404)
            return

        if not payload.get("stream"):
            answer = completion_payload(json.dumps(payload, ensure_ascii=False))
            self._json(
                {
                    "model": "smoke-fake",
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": json.dumps(answer, ensure_ascii=False),
                            },
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                }
            )
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()

        time.sleep(self.first_delay)
        for index, chunk in enumerate(self.chunks):
            frame = {
                "model": "smoke-fake",
                "choices": [{"index": 0, "delta": {"content": chunk}, "finish_reason": None}],
            }
            self.wfile.write(f"data: {json.dumps(frame, ensure_ascii=False)}\n\n".encode())
            self.wfile.flush()
            if index + 1 < len(self.chunks):
                time.sleep(self.chunk_delay)
        self.wfile.write(b'data: {"choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}\n\n')
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()
        self.close_connection = True


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="fake OpenAI-compatible SSE endpoint")
    # 它只作为 compose 服务运行，所以绑定所有网卡是刻意的。
    parser.add_argument("--host", default="0.0.0.0")  # noqa: S104
    parser.add_argument("--port", type=int, default=8081)
    parser.add_argument("--first-delay", type=float, default=2.0)
    parser.add_argument("--chunk-delay", type=float, default=0.2)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    FakeOpenAI.first_delay = args.first_delay
    FakeOpenAI.chunk_delay = args.chunk_delay
    server = ThreadingHTTPServer((args.host, args.port), FakeOpenAI)
    print(f"fake-openai listening on {args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
