"""T2: OpenAI-compatible adapter, driven by recorded DeepSeek samples (no network)."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator, Callable
from pathlib import Path

import httpx
import pytest

from better_resume.llm_gateway import (
    ChatRequest,
    ChatResult,
    ContentDelta,
    Done,
    FailureKind,
    LlmError,
    Message,
    ReasoningDelta,
    TokenUsage,
)
from better_resume.llm_gateway.adapters.openai_compat import OpenAICompatAdapter
from better_resume.llm_gateway.models import ModelSpec

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "llm"

SPEC = ModelSpec(
    name="deepseek-flash",
    provider="deepseek",
    base_url="https://api.deepseek.com",
    model_id="deepseek-flash",
    api_key_env="BR_DEEPSEEK_API_KEY",
    supports_reasoning=True,
)


def make_adapter(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    spec: ModelSpec = SPEC,
    api_key: str = "test-key",
    max_attempts: int = 3,
    sleeps: list[float] | None = None,
) -> OpenAICompatAdapter:
    async def record_sleep(seconds: float) -> None:
        if sleeps is not None:
            sleeps.append(seconds)

    return OpenAICompatAdapter(
        spec,
        api_key=api_key,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        max_attempts=max_attempts,
        sleep=record_sleep,
    )


def recorded(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


async def collect(stream: AsyncIterator[object]) -> list[object]:
    return [event async for event in stream]


def test_client_survives_malformed_no_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    # httpx parses NO_PROXY eagerly and chokes on bare IPv6 entries (common in WSL setups).
    # urllib only reads the FIRST *_proxy-suffixed "no_proxy" it finds (case-insensitive),
    # so the ambient variables must go: a benign lowercase no_proxy otherwise shadows the
    # malformed value and this test silently stops testing anything (found by the M6
    # acceptance run in a clean shell).
    for name in [key for key in os.environ if key.lower().endswith("_proxy")]:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("NO_PROXY", "[::1]")

    adapter = OpenAICompatAdapter(SPEC, api_key="k")

    assert adapter._client.trust_env is False  # noqa: SLF001 - asserting our own fallback
    asyncio.run(adapter.aclose())


def test_build_client_falls_back_when_httpx_rejects_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Deterministic twin of the test above: whatever the shell exports, a rejected proxy
    environment must still produce a usable client with trust_env=False."""
    attempts: list[dict[str, object]] = []
    real_client = httpx.AsyncClient

    def fake_client(*args: object, **kwargs: object) -> httpx.AsyncClient:
        attempts.append(dict(kwargs))
        if len(attempts) == 1:
            raise httpx.InvalidURL("Invalid port: ':1]'")
        return real_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", fake_client)

    adapter = OpenAICompatAdapter(SPEC, api_key="k")

    assert len(attempts) == 2, "the adapter must retry without the environment"
    assert attempts[1]["trust_env"] is False
    asyncio.run(adapter.aclose())


async def test_stream_normalizes_recorded_deepseek_frames() -> None:
    handler = lambda request: httpx.Response(200, content=recorded("deepseek_flash_stream.sse"))  # noqa: E731
    adapter = make_adapter(handler)

    events = await collect(
        adapter.stream(ChatRequest(messages=[Message(role="user", content="hi")]))
    )

    content = "".join(e.text for e in events if isinstance(e, ContentDelta))
    reasoning = "".join(e.text for e in events if isinstance(e, ReasoningDelta))

    assert content
    assert reasoning
    assert sum(isinstance(e, Done) for e in events) == 1
    assert isinstance(events[-1], Done)
    assert all(e.text for e in events if isinstance(e, (ContentDelta, ReasoningDelta)))


async def test_stream_sends_openai_payload_and_bearer_key() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, content=recorded("deepseek_flash_stream.sse"))

    adapter = make_adapter(handler)
    await collect(
        adapter.stream(ChatRequest(messages=[Message(role="user", content="你好")], model_ref=None))
    )

    assert seen["url"] == "https://api.deepseek.com/chat/completions"
    assert seen["auth"] == "Bearer test-key"
    body = seen["body"]
    assert isinstance(body, dict)
    assert body["model"] == "deepseek-flash"
    assert body["stream"] is True
    assert body["messages"] == [{"role": "user", "content": "你好"}]


async def test_stream_skips_dirty_frames() -> None:
    payload = b'data: {"oops\n\ndata: {"choices":[{"delta":{"content":"ok"}}]}\n\ndata: [DONE]\n\n'
    adapter = make_adapter(lambda request: httpx.Response(200, content=payload))

    events = await collect(adapter.stream(ChatRequest(messages=[])))

    assert "".join(e.text for e in events if isinstance(e, ContentDelta)) == "ok"
    assert isinstance(events[-1], Done)


async def test_stream_maps_http_5xx_to_retryable_error() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503, text="upstream busy")

    adapter = make_adapter(handler, max_attempts=3)

    with pytest.raises(LlmError) as error:
        await collect(adapter.stream(ChatRequest(messages=[])))

    assert error.value.kind is FailureKind.RETRYABLE
    assert calls["n"] == 3


async def test_stream_does_not_retry_client_errors() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(401, text="bad key")

    adapter = make_adapter(handler, max_attempts=3)

    with pytest.raises(LlmError) as error:
        await collect(adapter.stream(ChatRequest(messages=[])))

    assert error.value.kind is FailureKind.VENDOR
    assert error.value.status_code == 401
    assert calls["n"] == 1


async def test_stream_retries_timeout_then_succeeds() -> None:
    calls = {"n": 0}
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ReadTimeout("too slow")
        return httpx.Response(200, content=recorded("deepseek_flash_stream.sse"))

    adapter = make_adapter(handler, sleeps=sleeps)

    events = await collect(adapter.stream(ChatRequest(messages=[])))

    assert calls["n"] == 2
    assert len(sleeps) == 1
    assert isinstance(events[-1], Done)


async def test_complete_parses_recorded_json_response() -> None:
    adapter = make_adapter(
        lambda request: httpx.Response(200, content=recorded("deepseek_flash_json_object.json"))
    )

    result = await adapter.complete(ChatRequest(messages=[Message(role="user", content="hi")]))

    assert isinstance(result, ChatResult)
    assert json.loads(result.content) == {"ok": True, "n": 2}
    assert result.reasoning
    assert isinstance(result.usage, TokenUsage)
    assert result.usage.total_tokens == 102  # values recorded from the real response
    assert result.usage.reasoning_tokens == 23
