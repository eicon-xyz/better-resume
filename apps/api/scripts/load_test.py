"""M6-T6: a self-contained load test (asyncio + httpx) for the interview service.

    # against the compose stack (nginx in front of two api instances) with the local fake
    # upstream; nothing leaves this machine
    uv run python scripts/load_test.py --scenario mixed --concurrency 20 --requests 2000 \
        --fake-llm --json /tmp/m6.json

    # duration mode against the real vendor (no --fake-llm, so the report says upstream=real)
    uv run python scripts/load_test.py --scenario chat-sse --concurrency 5 --duration 30

Scenarios: `chat-sse` (concurrent streams, first-frame latency), `answer-submit` (the lock /
single-flight path), `mixed` (read + answer + stream, 60 / 25 / 15).

Exit codes: **0 means the run completed** — errors are data, not exit codes. 2 is a refused
configuration (a `--fake-llm` run pointed at a non-local host never sends a request), 3 means
the target stack could not be prepared (login or session setup failed).

What it measures: this service behind whatever sits in front of it. What it does not: model
latency (that is the vendor's) or anything about a machine it was not run on.
"""

from __future__ import annotations

import argparse
import asyncio
import itertools
import json
import sys
import time
import uuid
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "0.0.0.0"})  # noqa: S104 - targets
DEFAULT_BASE_URL = "http://127.0.0.1:8080"
DEFAULT_MODEL = "smoke-fake"
SCENARIOS = ("mixed", "chat-sse", "answer-submit")
# mixed is a fixed cycle (12 read / 5 answer / 3 chat), not a dice roll: two runs of the same
# size hit the same endpoints in the same proportions, which is what makes runs comparable.
MIX_PATTERN = (
    "chat",
    "read",
    "answer",
    "read",
    "read",
    "answer",
    "read",
    "chat",
    "read",
    "answer",
    "read",
    "read",
    "answer",
    "read",
    "chat",
    "read",
    "read",
    "answer",
    "read",
    "read",
)


class ConfigError(RuntimeError):
    """The arguments cannot produce an honest measurement."""


class SetupFailed(RuntimeError):
    """The target stack refused to prepare the scenario."""


def _percentile(sorted_values: Sequence[float], fraction: float) -> float:
    if not sorted_values:
        return 0.0
    index = min(len(sorted_values) - 1, int(len(sorted_values) * fraction))
    return round(sorted_values[index] * 1000, 2)


class Recorder:
    """Counts outcomes; percentiles come from the recorded wall-clock latencies."""

    def __init__(self, *, base_host: str = "") -> None:
        self.latencies: list[float] = []
        self.first_frames: list[float] = []
        self.ok = 0
        self.rate_limited = 0
        self.failures: dict[str, int] = {}
        self.hosts: set[str] = {base_host} if base_host else set()

    def _fail(self, kind: str) -> None:
        self.failures[kind] = self.failures.get(kind, 0) + 1

    def record(
        self,
        latency: float,
        status: int | None,
        *,
        host: str | None = None,
        kind: str | None = None,
        first_frame: float | None = None,
    ) -> None:
        self.latencies.append(latency)
        if host:
            self.hosts.add(host)
        if first_frame is not None:
            self.first_frames.append(first_frame)
        if status is not None and 200 <= status < 300:
            self.ok += 1
        elif status == 429:
            self.rate_limited += 1  # the limiter working is not an error
        elif status is not None:
            self._fail(f"http_{status}")
        else:
            self._fail(kind or "transport_error")

    @property
    def count(self) -> int:
        return len(self.latencies)

    def summary(self, *, duration: float) -> dict[str, Any]:
        latencies = sorted(self.latencies)
        first_frames = sorted(self.first_frames)
        failures = sum(self.failures.values())
        return {
            "count": self.count,
            "ok": self.ok,
            "rate_limited": self.rate_limited,
            "failure_kinds": dict(sorted(self.failures.items())),
            "error_rate": round(failures / self.count, 4) if self.count else 0.0,
            "rps": round(self.count / duration, 1) if duration > 0 else 0.0,
            "duration_s": round(duration, 2),
            "p50_ms": _percentile(latencies, 0.50),
            "p95_ms": _percentile(latencies, 0.95),
            "p99_ms": _percentile(latencies, 0.99),
            "max_ms": round(latencies[-1] * 1000, 2) if latencies else 0.0,
            "sse_first_frame_ms": {
                "count": len(first_frames),
                "p50_ms": _percentile(first_frames, 0.50),
                "p95_ms": _percentile(first_frames, 0.95),
                "p99_ms": _percentile(first_frames, 0.99),
                "max_ms": round(first_frames[-1] * 1000, 2) if first_frames else 0.0,
            },
        }


def _host_of(response: httpx.Response) -> str | None:
    request = getattr(response, "request", None)
    return request.url.host if request is not None else None


def _require(response: httpx.Response, what: str) -> None:
    if response.status_code >= 400:
        raise SetupFailed(f"{what} failed with HTTP {response.status_code}: {response.text[:200]}")
    if not response.content:
        raise SetupFailed(f"{what} returned no body")


def _model_body(model_ref: str | None, **extra: Any) -> dict[str, Any]:
    body: dict[str, Any] = dict(extra)
    if model_ref:
        body["model_ref"] = model_ref
    return body


async def login(client: httpx.AsyncClient, user_id: str) -> None:
    response = await client.post("/api/v1/auth/session", json={"user_id": user_id})
    _require(response, "login")


async def chat_stream(
    client: httpx.AsyncClient, session_id: str, recorder: Recorder, *, model_ref: str | None
) -> None:
    started = time.perf_counter()
    first_frame: float | None = None
    host: str | None = None
    try:
        async with client.stream(
            "POST",
            f"/api/v1/chat/sessions/{session_id}/stream",
            json=_model_body(model_ref, content=f"压测 {uuid.uuid4().hex[:8]}"),
        ) as response:
            host = _host_of(response)
            if response.status_code >= 400:
                recorder.record(time.perf_counter() - started, response.status_code, host=host)
                return
            async for line in response.aiter_lines():
                if line.startswith("event: content") and first_frame is None:
                    first_frame = time.perf_counter() - started
    except httpx.TimeoutException:
        recorder.record(time.perf_counter() - started, None, kind="timeout")
        return
    except httpx.HTTPError:
        recorder.record(time.perf_counter() - started, None, kind="transport_error")
        return
    recorder.record(time.perf_counter() - started, 200, host=host, first_frame=first_frame)


async def submit_answer(
    client: httpx.AsyncClient, session_id: str, recorder: Recorder, *, model_ref: str | None
) -> None:
    started = time.perf_counter()
    payload = _model_body(
        model_ref,
        question_no="1",
        answer=f"压测答案 {uuid.uuid4().hex[:8]}",
        request_id=uuid.uuid4().hex,
    )
    try:
        response = await client.post(
            f"/api/v1/interview/sessions/{session_id}/answers", json=payload
        )
    except httpx.TimeoutException:
        recorder.record(time.perf_counter() - started, None, kind="timeout")
        return
    except httpx.HTTPError:
        recorder.record(time.perf_counter() - started, None, kind="transport_error")
        return
    recorder.record(time.perf_counter() - started, response.status_code, host=_host_of(response))


async def read_sessions(client: httpx.AsyncClient, recorder: Recorder) -> None:
    started = time.perf_counter()
    try:
        response = await client.get("/api/v1/chat/sessions")
    except httpx.TimeoutException:
        recorder.record(time.perf_counter() - started, None, kind="timeout")
        return
    except httpx.HTTPError:
        recorder.record(time.perf_counter() - started, None, kind="transport_error")
        return
    recorder.record(time.perf_counter() - started, response.status_code, host=_host_of(response))


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


async def _create_chat_session(client: httpx.AsyncClient) -> str:
    response = await client.post("/api/v1/chat/sessions", json={"title": "load test"})
    _require(response, "create chat session")
    session_id = response.json().get("id")
    if not session_id:
        raise SetupFailed("create chat session returned no id")
    return str(session_id)


async def _create_interview(client: httpx.AsyncClient, *, model_ref: str | None) -> str:
    """Answers need a session with questions, so the lock/single-flight path has work to do."""
    created = await client.post("/api/v1/interview/sessions", json={})
    _require(created, "create interview session")
    session_id = created.json().get("id")
    if not session_id:
        raise SetupFailed("create interview session returned no id")
    data: dict[str, str] = {"count": "3"}
    if model_ref:
        data["model_ref"] = model_ref
    generated = await client.post(
        f"/api/v1/interview/sessions/{session_id}/questions",
        files={"file": ("cv.pdf", _tiny_pdf(), "application/pdf")},
        data=data,
    )
    _require(generated, "generate interview questions")
    return str(session_id)


async def prepare(
    client: httpx.AsyncClient, args: argparse.Namespace
) -> tuple[str | None, str | None]:
    await login(client, f"load-{uuid.uuid4().hex[:8]}")
    chat_id = await _create_chat_session(client) if args.scenario in ("chat-sse", "mixed") else None
    interview_id = (
        await _create_interview(client, model_ref=args.model)
        if args.scenario in ("answer-submit", "mixed")
        else None
    )
    return chat_id, interview_id


def make_action(
    args: argparse.Namespace,
    client: httpx.AsyncClient,
    chat_id: str | None,
    interview_id: str | None,
    recorder: Recorder,
) -> Callable[[], Awaitable[None]]:
    async def chat() -> None:
        await chat_stream(client, chat_id or "", recorder, model_ref=args.model)

    async def answer() -> None:
        await submit_answer(client, interview_id or "", recorder, model_ref=args.model)

    async def read() -> None:
        await read_sessions(client, recorder)

    if args.scenario == "chat-sse":
        return chat
    if args.scenario == "answer-submit":
        return answer

    counter = itertools.count()

    async def mixed() -> None:
        step = MIX_PATTERN[next(counter) % len(MIX_PATTERN)]
        if step == "read":
            await read()
        elif step == "answer":
            await answer()
        else:
            await chat()

    return mixed


async def drive(args: argparse.Namespace, action: Callable[[], Awaitable[None]]) -> None:
    concurrency = args.concurrency
    if args.requests is not None:
        share, extra = divmod(args.requests, concurrency)
        budgets = [share + (1 if index < extra else 0) for index in range(concurrency)]

        async def worker(budget: int) -> None:
            for _ in range(budget):
                await action()

        await asyncio.gather(*(worker(budget) for budget in budgets))
        return

    deadline = time.perf_counter() + args.duration

    async def loop() -> None:
        while time.perf_counter() < deadline:
            await action()

    await asyncio.gather(*(loop() for _ in range(concurrency)))


def resolve_base_url(args: argparse.Namespace) -> str:
    base_url = (args.base_url or DEFAULT_BASE_URL).rstrip("/")
    parts = urlsplit(base_url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ConfigError(f"--base-url must be an absolute http(s) URL, got {base_url!r}")
    if args.fake_llm and parts.hostname not in LOCAL_HOSTS:
        raise ConfigError(
            f"--fake-llm refuses {parts.hostname!r}: the fake upstream lives on this machine, "
            "so a remote target would silently measure the real vendor"
        )
    return base_url


async def run_scenario(
    args: argparse.Namespace, *, transport: httpx.AsyncBaseTransport | None = None
) -> dict[str, Any]:
    base_url = resolve_base_url(args)
    base_host = urlsplit(base_url).hostname or ""
    recorder = Recorder(base_host=base_host)
    limits = httpx.Limits(
        max_connections=max(16, args.concurrency * 2),
        max_keepalive_connections=max(8, args.concurrency),
    )
    async with httpx.AsyncClient(
        base_url=base_url,
        transport=transport,
        timeout=args.timeout,
        limits=limits,
        follow_redirects=False,
        # An ambient http_proxy/no_proxy must not sit in the path of a measurement (nor crash
        # the client on a bracketed no_proxy entry): the script talks to the target directly.
        trust_env=False,
    ) as client:
        chat_id, interview_id = await prepare(client, args)
        action = make_action(args, client, chat_id, interview_id, recorder)
        started = time.perf_counter()
        await drive(args, action)
        duration = time.perf_counter() - started

    if args.fake_llm and not recorder.hosts <= LOCAL_HOSTS:
        raise ConfigError(f"--fake-llm saw a request to {sorted(recorder.hosts - LOCAL_HOSTS)}")

    summary = recorder.summary(duration=duration)
    summary.update(
        {
            "scenario": args.scenario,
            "concurrency": args.concurrency,
            "mode": "requests" if args.requests is not None else "duration",
            "requested": args.requests if args.requests is not None else round(args.duration, 2),
            "upstream": "fake" if args.fake_llm else "real",
            "tag": args.tag or ("fake" if args.fake_llm else "real"),
            "fake_llm": bool(args.fake_llm),
            "model": args.model,
            "base_url": base_url,
            "target_hosts": sorted(recorder.hosts),
            "timeout_s": args.timeout,
        }
    )
    return summary


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="M6 load test (asyncio + httpx)")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--scenario", default="mixed", choices=list(SCENARIOS))
    parser.add_argument("--concurrency", type=int, default=10)
    budget = parser.add_mutually_exclusive_group()
    budget.add_argument("--requests", type=int, default=None, help="stop after this many requests")
    budget.add_argument("--duration", type=float, default=None, help="stop after this many seconds")
    parser.add_argument("--model", default=None, help="model_ref sent with every request")
    parser.add_argument("--fake-llm", action="store_true", help="local deterministic upstream")
    parser.add_argument(
        "--tag",
        default=None,
        help="label this run (e.g. real-model, saturation-c80) so reports never mix runs",
    )
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--json", default=None, help="write the summary here")
    args = parser.parse_args(argv)

    if args.requests is None and args.duration is None:
        args.duration = 10.0
    if args.concurrency < 1:
        parser.error("--concurrency must be >= 1")
    if args.requests is not None and args.requests < 1:
        parser.error("--requests must be >= 1")
    if args.duration is not None and args.duration <= 0:
        parser.error("--duration must be > 0")
    if args.model is None and args.fake_llm:
        args.model = DEFAULT_MODEL
    return args


SUMMARY_KEYS = (
    "tag",
    "scenario",
    "mode",
    "requested",
    "upstream",
    "model",
    "base_url",
    "target_hosts",
    "concurrency",
    "duration_s",
    "count",
    "ok",
    "rate_limited",
    "error_rate",
    "rps",
    "p50_ms",
    "p95_ms",
    "p99_ms",
    "max_ms",
    "sse_first_frame_ms",
    "failure_kinds",
)


def print_summary(summary: dict[str, Any]) -> None:
    print("\n=== M6 load test ===")
    for key in SUMMARY_KEYS:
        print(f"  {key:20s} {summary.get(key)}")


async def main(
    argv: Sequence[str] | None = None, *, transport: httpx.AsyncBaseTransport | None = None
) -> int:
    args = parse_args(argv)
    try:
        summary = await run_scenario(args, transport=transport)
    except (ConfigError, httpx.InvalidURL) as error:
        print(f"refused: {error}", file=sys.stderr)
        return 2
    except (SetupFailed, httpx.HTTPError) as error:
        print(f"could not prepare the run: {error}", file=sys.stderr)
        return 3

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
