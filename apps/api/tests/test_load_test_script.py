"""M6-T6: the load-test script's own logic is tested — never its performance.

There is no server and no network here: `httpx.MockTransport` is injected through the same
seam the script uses in production (`run_scenario(..., transport=...)`). The mock plays the
compose stack: the deterministic fake upstream (`--fake-llm`) answers instantly.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import httpx
import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
SSE_BODY = (
    'event: content\ndata: {"text": "片段0"}\n\n'
    'event: content\ndata: {"text": "片段1"}\n\n'
    'event: done\ndata: {"finish_reason": "stop"}\n\n'
).encode()

SUMMARY_FIELDS = (
    "count",
    "ok",
    "p50_ms",
    "p95_ms",
    "p99_ms",
    "max_ms",
    "rps",
    "duration_s",
    "error_rate",
    "rate_limited",
    "failure_kinds",
    "sse_first_frame_ms",
    "scenario",
    "concurrency",
    "model",
    "upstream",
    "target_hosts",
    "mode",
    "base_url",
)


def load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("m6_load_test", SCRIPTS / "load_test.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def load_test() -> ModuleType:
    return load_module()


class FakeUpstream:
    """The compose stack in miniature: fake LLM, instant and deterministic."""

    def __init__(
        self,
        *,
        status_map: dict[tuple[str, str], int] | None = None,
        raise_map: dict[tuple[str, str], Exception] | None = None,
    ) -> None:
        self.requests: list[httpx.Request] = []
        self.status_map = status_map or {}
        self.raise_map = raise_map or {}

    @property
    def hosts(self) -> set[str]:
        return {request.url.host for request in self.requests}

    def paths(self) -> list[str]:
        return [request.url.path for request in self.requests]

    def _rule(self, mapping: dict[tuple[str, str], object], request: httpx.Request):
        for (method, suffix), outcome in mapping.items():
            if request.method == method and request.url.path.endswith(suffix):
                return outcome
        return None

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        boom = self._rule(self.raise_map, request)
        if isinstance(boom, Exception):
            raise boom
        status = self._rule(self.status_map, request)
        if isinstance(status, int):
            return httpx.Response(status, json={"detail": "rejected by the fake stack"})

        path, method = request.url.path, request.method
        if path == "/api/v1/auth/session":
            return httpx.Response(201, json={"user_id": "load-user"})
        if path == "/api/v1/chat/sessions" and method == "POST":
            return httpx.Response(201, json={"id": "chat-1", "kind": "chat"})
        if path == "/api/v1/chat/sessions" and method == "GET":
            return httpx.Response(200, json=[])
        if path.endswith("/stream"):
            return httpx.Response(
                200, headers={"content-type": "text/event-stream"}, content=SSE_BODY
            )
        if path == "/api/v1/interview/sessions" and method == "POST":
            return httpx.Response(201, json={"id": "interview-1", "status": "ready"})
        if path.endswith("/questions"):
            return httpx.Response(
                201,
                json={
                    "session": {"id": "interview-1"},
                    "questions": [{"question_no": "1", "topic_no": 1, "text": "讲讲你的项目"}],
                },
            )
        if path.endswith("/answers"):
            return httpx.Response(201, json={"question_no": "1", "score": 80})
        return httpx.Response(404, json={"detail": f"no route for {method} {path}"})


async def run_script(
    load_test: ModuleType, tmp_path: Path, upstream: FakeUpstream, *extra: str
) -> tuple[int, dict]:
    output = tmp_path / "summary.json"
    code = await load_test.main(
        [
            "--base-url",
            "http://127.0.0.1:8080",
            "--scenario",
            "mixed",
            "--concurrency",
            "3",
            "--requests",
            "6",
            "--model",
            "smoke-fake",
            "--fake-llm",
            *extra,
            "--json",
            str(output),
        ],
        transport=httpx.MockTransport(upstream),
    )
    assert code == 0, "exit code 0 means the run completed, not that nothing failed"
    return code, json.loads(output.read_text(encoding="utf-8"))


async def test_tiny_run_reports_every_metric(load_test: ModuleType, tmp_path: Path) -> None:
    upstream = FakeUpstream()
    _, summary = await run_script(load_test, tmp_path, upstream)

    for field in SUMMARY_FIELDS:
        assert field in summary, field
    for field in ("count", "p50_ms", "p95_ms", "p99_ms"):
        assert field in summary["sse_first_frame_ms"], field

    assert summary["count"] == 6, "every requested iteration is accounted for"
    assert summary["mode"] == "requests"
    assert summary["ok"] == 6
    assert summary["failure_kinds"] == {}
    assert summary["error_rate"] == 0.0
    assert summary["p95_ms"] >= summary["p50_ms"] >= 0
    assert summary["sse_first_frame_ms"]["count"] >= 1, "the mixed scenario must stream chat"
    assert summary["sse_first_frame_ms"]["p50_ms"] > 0


async def test_rate_limited_429_is_counted_and_the_run_still_finishes(
    load_test: ModuleType, tmp_path: Path
) -> None:
    upstream = FakeUpstream(
        status_map={
            ("GET", "/sessions"): 429,
            ("POST", "/stream"): 429,
            ("POST", "/answers"): 429,
        }
    )
    _, summary = await run_script(load_test, tmp_path, upstream)

    assert summary["rate_limited"] == summary["count"] > 0
    assert summary["ok"] == 0
    assert summary["error_rate"] == 0.0, "429 is the limiter working, not a failure"
    assert summary["failure_kinds"] == {}


async def test_fake_llm_run_never_leaves_the_local_host(
    load_test: ModuleType, tmp_path: Path
) -> None:
    upstream = FakeUpstream()
    _, summary = await run_script(load_test, tmp_path, upstream)

    assert summary["upstream"] == "fake", "the report must say the upstream was the fake one"
    assert summary["model"] == "smoke-fake"
    assert set(summary["target_hosts"]) <= LOCAL_HOSTS
    assert upstream.hosts == {"127.0.0.1"}, "no request may go anywhere else"
    assert upstream.requests, "the run did talk to the (fake) stack"


async def test_fake_llm_refuses_a_remote_target(load_test: ModuleType, tmp_path: Path) -> None:
    upstream = FakeUpstream()
    output = tmp_path / "refused.json"
    code = await load_test.main(
        [
            "--base-url",
            "https://api.deepseek.com",
            "--scenario",
            "chat-sse",
            "--requests",
            "1",
            "--fake-llm",
            "--json",
            str(output),
        ],
        transport=httpx.MockTransport(upstream),
    )

    assert code != 0, "a fake-LLM run pointed at a vendor must fail loudly"
    assert upstream.requests == [], "it must refuse before the first request"
    assert not output.exists()


async def test_failure_kinds_and_error_rate_are_honest(
    load_test: ModuleType, tmp_path: Path
) -> None:
    broken_stream = FakeUpstream(raise_map={("POST", "/stream"): httpx.ConnectError("reset")})
    _, streaming = await run_script(
        load_test, tmp_path, broken_stream, "--scenario", "chat-sse", "--requests", "4"
    )
    assert streaming["count"] == 4
    assert streaming["failure_kinds"] == {"transport_error": 4}
    assert streaming["error_rate"] == 1.0
    assert streaming["ok"] == 0

    broken_answers = FakeUpstream(status_map={("POST", "/answers"): 500})
    _, answers = await run_script(
        load_test, tmp_path, broken_answers, "--scenario", "answer-submit", "--requests", "5"
    )
    assert answers["failure_kinds"] == {"http_500": 5}
    assert answers["error_rate"] == round(5 / answers["count"], 4)
    assert answers["p95_ms"] >= answers["p50_ms"] >= 0


async def test_duration_mode_stops_after_the_deadline(
    load_test: ModuleType, tmp_path: Path
) -> None:
    upstream = FakeUpstream()
    output = tmp_path / "duration.json"
    code = await load_test.main(
        [
            "--base-url",
            "http://127.0.0.1:8080",
            "--scenario",
            "mixed",
            "--concurrency",
            "2",
            "--duration",
            "0.3",
            "--fake-llm",
            "--json",
            str(output),
        ],
        transport=httpx.MockTransport(upstream),
    )
    summary = json.loads(output.read_text(encoding="utf-8"))

    assert code == 0
    assert summary["mode"] == "duration"
    assert summary["count"] > 0
    assert summary["duration_s"] <= 5.0
