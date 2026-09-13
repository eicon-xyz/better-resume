"""M6-T6: load test — measured numbers only, in-process or against a real server.

    # in-process (no uvicorn/nginx in the path; the honest "app throughput" number)
    uv run python scripts/load_test.py --scenario mixed --concurrency 20 --fake-llm
    uv run python scripts/load_test.py --scenario chat-sse --concurrency 20 --duration 15

    # against the compose stack through nginx
    uv run python scripts/load_test.py --base-url http://127.0.0.1:8080 --concurrency 10

What it measures: latency percentiles, RPS, error rate, 429s, SSE first-frame latency.
What it does NOT measure: model latency (that is the vendor's), nginx/uvicorn overhead in
in-process mode, multi-machine behaviour.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import statistics
import time
import uuid
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import httpx

from better_resume.llm_gateway import (
    ChatRequest,
    ChatResult,
    ContentDelta,
    Done,
    StreamEvent,
    VendorMeta,
)
from better_resume.main import create_app
from better_resume.settings import Settings


class FakeGateway:
    """Deterministic vendor: keeps the measurement about *our* code, not the model."""

    def __init__(self, *, delay_ms: float = 0.0, chunks: int = 4) -> None:
        self.delay = delay_ms / 1000
        self.chunks = chunks
        self.calls = 0

    def stream(self, request: ChatRequest) -> AsyncIterator[StreamEvent]:
        return self._stream(request)

    async def _stream(self, request: ChatRequest) -> AsyncIterator[StreamEvent]:
        self.calls += 1
        for index in range(self.chunks):
            if self.delay:
                await asyncio.sleep(self.delay)
            await asyncio.sleep(0)
            yield ContentDelta(text=f"片段{index}")
        yield VendorMeta(model="fake", extra={"usage": {"total_tokens": 8}})
        yield Done(finish_reason="stop")

    async def complete(self, request: ChatRequest) -> ChatResult:
        self.calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        payload = '{"score": 80, "feedback": "ok", "missing_points": []}'
        return ChatResult(content=payload, model="fake", parsed=None)


class Recorder:
    def __init__(self) -> None:
        self.latencies: list[float] = []
        self.first_frames: list[float] = []
        self.ok = 0
        self.expected = 0
        self.errors: dict[str, int] = {}
        self.too_many_requests = 0
        self._lock = asyncio.Lock()

    async def record(self, latency: float, status: int) -> None:
        async with self._lock:
            self.latencies.append(latency)
            if status < 400:
                self.ok += 1
            elif status == 429:
                self.too_many_requests += 1
                self.expected += 1
            elif status in (409, 404):
                self.expected += 1  # legitimate outcomes for racy answers
            else:
                self.errors[str(status)] = self.errors.get(str(status), 0) + 1

    def summary(self, *, duration: float) -> dict[str, Any]:
        latencies = sorted(self.latencies)
        total = len(latencies)

        def percentile(fraction: float) -> float:
            if not latencies:
                return 0.0
            index = min(len(latencies) - 1, int(len(latencies) * fraction))
            return round(latencies[index] * 1000, 2)

        failures = sum(self.errors.values())
        return {
            "requests": total,
            "ok": self.ok,
            "expected_non_2xx": self.expected,
            "errors": self.errors,
            "rate_limited": self.too_many_requests,
            "error_rate": round(failures / total, 4) if total else 0.0,
            "rps": round(total / duration, 1) if duration > 0 else 0.0,
            "p50_ms": percentile(0.5),
            "p95_ms": percentile(0.95),
            "p99_ms": percentile(0.99),
            "max_ms": round((max(latencies) * 1000) if latencies else 0.0, 2),
            "sse_first_frame_p50_ms": round(
                (statistics.median(self.first_frames) * 1000) if self.first_frames else 0.0, 2
            ),
            "duration_s": round(duration, 2),
        }


async def login(client: httpx.AsyncClient, user_id: str) -> None:
    response = await client.post("/api/v1/auth/session", json={"user_id": user_id})
    response.raise_for_status()


async def chat_stream(
    client: httpx.AsyncClient, session_id: str, recorder: Recorder, content: str
) -> None:
    started = time.perf_counter()
    first_frame: float | None = None
    status = 200
    try:
        async with client.stream(
            "POST",
            f"/api/v1/chat/sessions/{session_id}/stream",
            json={"content": content},
        ) as response:
            status = response.status_code
            if status < 400:
                async for line in response.aiter_lines():
                    if line.startswith("event: content") and first_frame is None:
                        first_frame = time.perf_counter() - started
    except httpx.HTTPError:
        status = 599
    elapsed = time.perf_counter() - started
    await recorder.record(elapsed, status)
    if first_frame is not None:
        recorder.first_frames.append(first_frame)


async def answer_submit(
    client: httpx.AsyncClient, session_id: str, recorder: Recorder, user_id: str
) -> None:
    started = time.perf_counter()
    status = 200
    try:
        response = await client.post(
            f"/api/v1/interview/sessions/{session_id}/answers",
            json={
                "question_no": "1",
                "answer": f"压测答案 {uuid.uuid4().hex[:8]}",
                "request_id": uuid.uuid4().hex,
            },
        )
        status = response.status_code
    except httpx.HTTPError:
        status = 599
    await recorder.record(time.perf_counter() - started, status)


async def read_endpoint(client: httpx.AsyncClient, recorder: Recorder) -> None:
    started = time.perf_counter()
    status = 200
    try:
        response = await client.get("/api/v1/chat/sessions")
        status = response.status_code
    except httpx.HTTPError:
        status = 599
    await recorder.record(time.perf_counter() - started, status)


async def prepare_interview(client: httpx.AsyncClient) -> str | None:
    """A finished-ish interview with questions, so the answers endpoint has work to do."""
    created = await client.post("/api/v1/interview/sessions", json={})
    if created.status_code != 201:
        return None
    session_id = created.json()["id"]
    pdf = _tiny_pdf()
    generated = await client.post(
        f"/api/v1/interview/sessions/{session_id}/questions",
        files={"file": ("cv.pdf", pdf, "application/pdf")},
        data={"count": "3"},
    )
    return session_id if generated.status_code == 201 else None


def _tiny_pdf() -> bytes:
    """A resume the parser can actually read (CJK font, one project bullet)."""
    import io

    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfgen import canvas

    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.setFont("STSong-Light", 12)
    for index, line in enumerate(
        (
            "张三 13800138000 zhangsan@example.com",
            "教育经历",
            "某大学 计算机科学与技术 2018-2022",
            "项目经历",
            "订单写入链路重构",
            "- 批量写入把 P99 从 800ms 降到 120ms",
            "技能特长",
            "Python FastAPI PostgreSQL Redis",
        )
    ):
        pdf.drawString(60, 780 - index * 20, line)
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def make_worker(
    scenario: str,
    client: httpx.AsyncClient,
    session_id: str | None,
    interview_id: str | None,
    recorder: Recorder,
    user_id: str,
) -> Callable[[], Any]:
    async def worker() -> None:
        if scenario == "chat-sse":
            await chat_stream(client, session_id or "", recorder, uuid.uuid4().hex)
        elif scenario == "answer-submit":
            await answer_submit(client, interview_id or "", recorder, user_id)
        else:
            roll = random.random()  # noqa: S311 - load shaping, not crypto
            if roll < 0.7:
                await read_endpoint(client, recorder)
            elif roll < 0.9 and interview_id:
                await answer_submit(client, interview_id, recorder, user_id)
            else:
                await chat_stream(client, session_id or "", recorder, uuid.uuid4().hex)

    return worker


def _load_env() -> None:
    """Same convention as the other smoke scripts: the repo .env provides URLs/keys."""
    from dotenv import load_dotenv

    for candidate in (Path(".env"), Path("../../.env")):
        if candidate.exists():
            load_dotenv(candidate, override=False)


async def _reset_scene_bindings(settings: Settings) -> None:
    """Scene bindings are global state: a leftover test binding would skew the run."""
    import sqlalchemy as sa
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(settings.database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                sa.text(
                    "UPDATE llm_scene_bindings SET adapter = :adapter, "
                    "target_ref = :target "
                    "WHERE adapter <> :adapter OR target_ref <> :target"
                ),
                {"adapter": "openai_compat", "target": "deepseek-flash"},
            )
    finally:
        await engine.dispose()


async def run(args: argparse.Namespace) -> dict[str, Any]:
    _load_env()
    settings = Settings(_env_file=None)
    if args.rate_limit_off:
        settings = settings.model_copy(
            update={"rate_limit": settings.rate_limit.model_copy(update={"enabled": False})}
        )
    app = create_app(settings)
    fake = FakeGateway(delay_ms=args.llm_delay_ms)
    os.environ.setdefault("BR_DEEPSEEK_API_KEY", "sk-load-test-fake")

    recorder = Recorder()
    user_id = f"load-{uuid.uuid4().hex[:8]}"

    if args.base_url:
        transport: httpx.AsyncBaseTransport | None = None
        base_url = args.base_url
    else:
        transport = httpx.ASGITransport(app=app)
        base_url = "http://loadtest"

    async with app.router.lifespan_context(app):
        if not args.base_url:
            await _reset_scene_bindings(settings)
        if args.fake_llm or not args.base_url:
            app.state.llm_gateway_factory = lambda spec, api_key: fake
        async with httpx.AsyncClient(
            transport=transport, base_url=base_url, timeout=30.0
        ) as client:
            await login(client, user_id)
            chat_session = await client.post("/api/v1/chat/sessions", json={"title": "load"})
            session_id = chat_session.json().get("id") if chat_session.status_code == 201 else None
            interview_id = None
            if args.scenario in ("answer-submit", "mixed"):
                interview_id = await prepare_interview(client)

            worker = make_worker(args.scenario, client, session_id, interview_id, recorder, user_id)
            started = time.perf_counter()
            deadline = started + args.duration

            async def loop() -> None:
                while time.perf_counter() < deadline:
                    await worker()

            await asyncio.gather(*(loop() for _ in range(args.concurrency)))
            duration = time.perf_counter() - started

    summary = recorder.summary(duration=duration)
    summary.update(
        {
            "scenario": args.scenario,
            "concurrency": args.concurrency,
            "transport": "http" if args.base_url else "in-process ASGI",
            "fake_llm": bool(args.fake_llm or not args.base_url),
            "fake_llm_calls": fake.calls,
            "rate_limit": "off" if args.rate_limit_off else "on",
            "llm_delay_ms": args.llm_delay_ms,
        }
    )
    return summary


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scenario", default="mixed", choices=["mixed", "chat-sse", "answer-submit"]
    )
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--duration", type=float, default=10.0)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--fake-llm", action="store_true")
    parser.add_argument("--llm-delay-ms", type=float, default=0.0)
    parser.add_argument("--rate-limit-off", action="store_true")
    parser.add_argument("--json", default=None)
    return parser.parse_args(argv)


def print_summary(summary: dict[str, Any]) -> None:
    print("\n=== M6 load test ===")
    for key in (
        "scenario",
        "transport",
        "concurrency",
        "duration_s",
        "requests",
        "rps",
        "p50_ms",
        "p95_ms",
        "p99_ms",
        "max_ms",
        "sse_first_frame_p50_ms",
        "ok",
        "expected_non_2xx",
        "rate_limited",
        "error_rate",
        "errors",
        "fake_llm",
        "fake_llm_calls",
        "rate_limit",
    ):
        print(f"  {key:24s} {summary.get(key)}")


async def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    summary = await run(args)
    print_summary(summary)
    if args.json:
        await asyncio.to_thread(
            Path(args.json).write_text,
            json.dumps(summary, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"  json -> {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
