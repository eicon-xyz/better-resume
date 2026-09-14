"""V1: the real-vendor smoke's own logic, driven by a mock vendor (no network, no key)."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from scripts import real_model_smoke


def test_parse_meta_only_accepts_the_vendor_frame() -> None:
    assert real_model_smoke.parse_meta(
        'data: {"model": "deepseek-flash", "usage": {"total_tokens": 7}}'
    ) == {
        "model": "deepseek-flash",
        "usage": {"total_tokens": 7},
    }
    assert real_model_smoke.parse_meta('data: {"text": "你好"}') is None
    assert real_model_smoke.parse_meta("event: content") is None
    assert real_model_smoke.parse_meta("data: not-json") is None


def test_summarise_steps_reports_failures_models_and_tokens() -> None:
    steps = [
        {"name": "login", "ok": True, "ms": 10},
        {
            "name": "chat-stream",
            "ok": True,
            "ms": 20,
            "model": "deepseek-flash",
            "usage": {"total_tokens": 30},
        },
        {"name": "finish", "ok": False, "ms": 5},
    ]

    summary = real_model_smoke.summarise_steps(steps)

    assert summary["steps"] == 3
    assert summary["failed"] == ["finish"]
    assert summary["models"] == ["deepseek-flash"]
    assert summary["total_tokens"] == 30
    assert summary["total_ms"] == 35.0


def _sse(*frames: str) -> bytes:
    return "".join(frames).encode()


def mock_vendor(*, with_meta: bool = True) -> httpx.MockTransport:
    """A vendor that answers every endpoint the script touches."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/v1/auth/session":
            return httpx.Response(200, json={"user_id": "v1"})
        if path == "/api/v1/chat/sessions" and request.method == "POST":
            return httpx.Response(200, json={"id": "chat-1"})
        if path.endswith("/stream"):
            body = _sse(
                'event: content\ndata: {"text": "我适合"}\n\n',
                'event: meta\ndata: {"model": "deepseek-flash", "usage": {"total_tokens": 42}}\n\n'
                if with_meta
                else ": ping\n\n",
                'event: done\ndata: {"finish_reason": "stop"}\n\n',
            )
            return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body)
        if path == "/api/v1/interview/sessions" and request.method == "POST":
            return httpx.Response(200, json={"id": "interview-1"})
        if path.endswith("/questions"):
            return httpx.Response(
                200,
                json={
                    "questions": [
                        {
                            "question_no": str(index),
                            "topic": f"t{index}",
                            "focus_points": ["f"],
                            "text": f"q{index}",
                        }
                        for index in range(1, 4)
                    ],
                    "session": {"resume_score": 70.0},
                },
            )
        if path.endswith("/restore"):
            return httpx.Response(200, json={"flow": {"current_question_no": None}, "answered": 3})
        if path.endswith("/answers"):
            return httpx.Response(
                200,
                json={
                    "answer": {"score": 80.0, "follow_up_reason": None},
                    "next_action": "finished",
                },
            )
        if path.endswith("/finish"):
            return httpx.Response(
                200,
                json={
                    "overall_score": 80.0,
                    "turns": [{"question_no": "1"}],
                    "summary_pending": True,
                },
            )
        if path.endswith("/report"):
            return httpx.Response(200, json={"summary": "整体不错", "overall_score": 80.0})
        raise AssertionError(f"unexpected request: {request.method} {path}")

    return httpx.MockTransport(handler)


def run_args(**overrides: object) -> object:
    args = real_model_smoke.parse_args(["--base-url", "http://mock", "--summary-timeout", "1"])
    for key, value in overrides.items():
        setattr(args, key, value)
    return args


async def test_run_passes_against_a_vendor_that_reports_its_model() -> None:
    exit_code = await real_model_smoke.run(run_args(), transport=mock_vendor())

    assert exit_code == 0


async def test_run_fails_when_the_vendor_never_reports_usage() -> None:
    # The fake vendor sends no usage: that is exactly how this script tells real from fake.
    exit_code = await real_model_smoke.run(run_args(), transport=mock_vendor(with_meta=False))

    assert exit_code == 1


def test_failure_probe_is_skipped_without_docker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("scripts.real_model_smoke.shutil.which", lambda name: None)

    assert real_model_smoke.ensure_broken_model() is False


def test_script_never_lets_a_proxy_swallow_the_loopback_traffic() -> None:
    text = Path(real_model_smoke.__file__).read_text(encoding="utf-8")

    assert "trust_env=False" in text
