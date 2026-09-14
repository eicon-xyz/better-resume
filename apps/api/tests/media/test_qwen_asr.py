"""V3: the batch ASR channel (qwen-audio-3.0-asr-flash) built against a fake vendor."""

from __future__ import annotations

import asyncio
import base64
import json
import wave
from io import BytesIO

import httpx
import pytest

from better_resume.media import ChannelCtx, TranscriptEvent
from better_resume.media.adapters import (
    MediaConfigError,
    QwenAsrFlashAdapter,
    build_client,
    parse_text,
    pcm_to_wav,
    to_data_uri,
)

ENDPOINT = "https://example.invalid/api/v1/services/aigc/multimodal-generation/generation"
SAMPLE_PCM = b"\x00\x01" * 1600  # 3200 bytes = 100 ms of 16 kHz mono s16le
VENDOR_TEXT = "你好，我是来自示例大学人工智能本科的测试用户。"


def build_adapter(
    handler, *, api_key: str = "sk-test", endpoint: str = ENDPOINT
) -> tuple[QwenAsrFlashAdapter, list[TranscriptEvent]]:
    events: list[TranscriptEvent] = []
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = QwenAsrFlashAdapter(
        api_key=api_key, endpoint=endpoint, on_event=events.append, client=client
    )
    return adapter, events


async def feed_and_stop(adapter: QwenAsrFlashAdapter, pcm: bytes = SAMPLE_PCM) -> None:
    await adapter.start(ChannelCtx(session_id="v3"))
    await adapter.feed(pcm)
    await adapter.stop()


def wav_payload(pcm: bytes, *, sample_rate: int = 16000) -> tuple[int, int, int, bytes]:
    with wave.open(BytesIO(pcm), "rb") as handle:
        return (
            handle.getnchannels(),
            handle.getframerate(),
            handle.getsampwidth() * 8,
            handle.readframes(handle.getnframes()),
        )


async def test_request_is_a_data_uri_wav_the_vendor_accepts() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        captured["sse"] = request.headers.get("x-dashscope-sse")
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"text": VENDOR_TEXT, "sentence": {"text": VENDOR_TEXT}})

    adapter, events = build_adapter(handler)
    await feed_and_stop(adapter)

    assert captured["url"] == ENDPOINT
    assert captured["auth"] == "Bearer sk-test"
    assert captured["sse"] == "disable"
    body = captured["body"]
    assert body["model"] == "qwen-audio-3.0-asr-flash"
    assert body["parameters"] == {"format": "wav", "sample_rate": "16000"}
    data = body["input"]["messages"][0]["content"][0]["input_audio"]["data"]
    assert data.startswith("data:audio/wav;base64,")
    channels, rate, bits, payload = wav_payload(base64.b64decode(data.split(",", 1)[1]))
    assert (channels, rate, bits) == (1, 16000, 16)
    assert payload == SAMPLE_PCM
    assert [event.text for event in events] == [VENDOR_TEXT]
    assert events[0].kind == "final"


async def test_wait_blocks_until_stop_finished() -> None:
    """The WS endpoint closes the socket as soon as wait() returns, so a batch channel must
    not report "ended" while the audio is still being transcribed (regression: the first
    implementation returned immediately and the socket died on the client's first frame)."""
    release = asyncio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        await release.wait()
        return httpx.Response(200, json={"text": VENDOR_TEXT})

    adapter, events = build_adapter(handler)
    await adapter.start(ChannelCtx(session_id="v3"))
    await adapter.feed(SAMPLE_PCM)

    waiter = asyncio.create_task(adapter.wait())
    await asyncio.sleep(0.05)
    assert not waiter.done(), "wait() returned before the channel ended"

    stopper = asyncio.create_task(adapter.stop())
    await asyncio.sleep(0.05)
    assert not stopper.done()
    release.set()
    await asyncio.wait_for(stopper, timeout=5)
    await asyncio.wait_for(waiter, timeout=5)
    assert [event.text for event in events] == [VENDOR_TEXT]


async def test_a_hostile_proxy_environment_does_not_break_the_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WSL exports a bare IPv6 NO_PROXY; httpx raises while parsing it during construction."""
    attempts: list[dict[str, object]] = []
    real_client = httpx.AsyncClient

    def fake_client(*args: object, **kwargs: object) -> httpx.AsyncClient:
        attempts.append(dict(kwargs))
        if len(attempts) == 1:
            raise httpx.InvalidURL("Invalid port: ':1]'")
        return real_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", fake_client)
    client = build_client(5.0)

    assert len(attempts) == 2
    assert attempts[1]["trust_env"] is False
    await client.aclose()


async def test_empty_audio_never_calls_the_vendor() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - must not run
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"text": "should not happen"})

    adapter, events = build_adapter(handler)

    await adapter.start(ChannelCtx(session_id="v3"))
    await adapter.stop()

    assert calls == 0
    assert events == []


async def test_vendor_error_is_recorded_and_raised() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "invalid api key"}})

    adapter, events = build_adapter(handler)

    with pytest.raises(MediaConfigError, match="401"):
        await feed_and_stop(adapter)

    assert isinstance(adapter.failure, MediaConfigError)
    assert events == []


async def test_timeout_is_a_recorded_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("too slow", request=request)

    adapter, events = build_adapter(handler)

    with pytest.raises(MediaConfigError, match="request failed"):
        await feed_and_stop(adapter)

    assert adapter.failure is not None
    assert events == []


async def test_feed_after_stop_is_ignored_and_stop_is_idempotent() -> None:
    bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"text": VENDOR_TEXT})

    adapter, events = build_adapter(handler)
    await feed_and_stop(adapter)

    await adapter.feed(SAMPLE_PCM)
    await adapter.stop()

    assert len(bodies) == 1
    assert len(events) == 1


async def test_missing_configuration_is_reported_not_guessed() -> None:
    with pytest.raises(MediaConfigError, match="BR_DASHSCOPE_API_KEY"):
        QwenAsrFlashAdapter(api_key="", endpoint=ENDPOINT, on_event=lambda event: None)
    with pytest.raises(MediaConfigError, match="BR_MEDIA__ASR_URL"):
        QwenAsrFlashAdapter(api_key="sk", endpoint="", on_event=lambda event: None)


def test_helpers_are_boringly_predictable() -> None:
    wav = pcm_to_wav(SAMPLE_PCM)
    assert wav[:4] == b"RIFF" and wav[8:12] == b"WAVE"
    assert to_data_uri(wav).startswith("data:audio/wav;base64,")
    assert parse_text({"text": " hi "}) == "hi"
    assert parse_text({"output": {"text": "there"}}) == "there"
    assert parse_text({"sentence": {"text": "sentence"}}) == "sentence"
    assert parse_text({}) == ""
