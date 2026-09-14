"""P1-A: the Paraformer realtime channel, built against a scripted fake vendor.

Wire contract verified against the live workspace endpoint (2026-09-15 preflight):
wss://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/api-ws/v1/inference, Bearer auth at the
handshake, run-task / binary PCM frames / finish-task, incremental result-generated events.

The fake is reactive on purpose: task-started follows run-task, and task-finished is only
released after the client sent finish-task — the vendor never ends a task unprompted.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from better_resume.ai_resilience import AiUnavailable
from better_resume.media import ChannelCtx, TranscriptEvent
from better_resume.media.adapters import (
    MediaConfigError,
    ParaformerRealtimeAdapter,
    derive_realtime_ws_url,
)
from better_resume.settings import MediaSettings

WS_URL = "wss://ws-3foqfy9ysbn66ik2.cn-beijing.maas.aliyuncs.com/api-ws/v1/inference"
BATCH_URL = (
    "https://ws-3foqfy9ysbn66ik2.cn-beijing.maas.aliyuncs.com"
    "/api/v1/services/aigc/multimodal-generation/generation"
)
FULL = "你好，我是来自示例大学人工智能本科的测试用户。"
#: Non-silent filler PCM; assertions derive the frame count from its length.
SAMPLE_PCM = bytes(range(1, 255)) * 32


class FakeVendor:
    """Minimal duplex websocket: reactive task lifecycle, captured client frames."""

    def __init__(self, results: list[str], *, finish: bool = True) -> None:
        self.results = list(results)
        self.finishes = finish
        self.client_frames: list[str | bytes] = []
        self.task_id = ""
        self.finish_seen = False
        self.started_sent = False
        self.closed = False

    async def send(self, frame: str | bytes) -> None:
        self.client_frames.append(frame)
        if isinstance(frame, bytes):
            return
        header = json.loads(frame).get("header", {})
        if header.get("action") == "run-task":
            self.task_id = str(header.get("task_id"))
            self.started_sent = True
        elif header.get("action") == "finish-task":
            self.finish_seen = True

    async def recv(self) -> str:
        while True:
            if self.started_sent:
                self.started_sent = False
                return started_frame(self.task_id)
            if self.results:
                return self.results.pop(0)
            if self.finish_seen and self.finishes:
                return finished_frame(self.task_id)
            await asyncio.sleep(0.01)

    async def close(self) -> None:
        self.closed = True


def build_adapter(
    results: list[str],
    *,
    api_key: str = "sk-test",
    ws_url: str = WS_URL,
    connection: FakeVendor | None = None,
    **kwargs: Any,
) -> tuple[ParaformerRealtimeAdapter, list[TranscriptEvent], FakeVendor]:
    events: list[TranscriptEvent] = []
    finish = kwargs.pop("finish", True)  # FakeVendor knob, not an adapter knob
    vendor = connection or FakeVendor(results, finish=finish)
    opened: dict[str, Any] = {}

    async def fake_open(url: str, headers: dict[str, str], open_timeout: float) -> FakeVendor:
        opened["url"] = url
        opened["auth"] = headers.get("Authorization")
        opened["open_timeout"] = open_timeout
        return vendor

    adapter = ParaformerRealtimeAdapter(
        api_key=api_key,
        ws_url=ws_url,
        on_event=events.append,
        connect=fake_open,  # type: ignore[arg-type]
        **kwargs,
    )
    adapter.opened = opened  # type: ignore[attr-defined]
    return adapter, events, vendor


async def run_press(adapter: ParaformerRealtimeAdapter, pcm: bytes = SAMPLE_PCM) -> None:
    await adapter.start(ChannelCtx(session_id="p1a"))
    if pcm:
        await adapter.feed(pcm)
        await asyncio.sleep(0.05)  # let the session task stream the buffered audio
    await adapter.stop()


def result_generated(text: str, *, end: bool) -> str:
    return json.dumps(
        {
            "header": {"event": "result-generated", "task_id": "t"},
            "payload": {"output": {"sentence": {"text": text, "sentence_end": end}}},
        }
    )


def started_frame(task_id: str = "t") -> str:
    return json.dumps({"header": {"event": "task-started", "task_id": task_id}})


def finished_frame(task_id: str = "t") -> str:
    return json.dumps({"header": {"event": "task-finished", "task_id": task_id}})


def failed_frame(code: str, message: str) -> str:
    return json.dumps(
        {
            "header": {
                "event": "task-failed",
                "task_id": "t",
                "error_code": code,
                "error_message": message,
            }
        }
    )


def text_frames(vendor: FakeVendor) -> list[dict[str, Any]]:
    return [json.loads(frame) for frame in vendor.client_frames if isinstance(frame, str)]


async def test_run_task_frame_matches_the_vendor_contract() -> None:
    adapter, _events, vendor = build_adapter([])
    await run_press(adapter)

    run_task = text_frames(vendor)[0]
    assert adapter.opened["url"] == WS_URL
    assert adapter.opened["auth"] == "Bearer sk-test"
    header = run_task["header"]
    assert header["action"] == "run-task"
    assert len(header["task_id"]) == 32
    assert header["streaming"] == "duplex"
    payload = run_task["payload"]
    assert payload["model"] == "paraformer-realtime-v2"
    assert (payload["task_group"], payload["task"], payload["function"]) == (
        "audio",
        "asr",
        "recognition",
    )
    assert payload["parameters"] == {"format": "pcm", "sample_rate": 16000}
    assert payload["input"] == {}


async def test_partials_map_to_replace_archive_and_final() -> None:
    results = [
        result_generated("", end=False),
        result_generated("你", end=False),
        result_generated("你好，我是来自", end=False),
        result_generated(FULL, end=True),
    ]
    adapter, events, _vendor = build_adapter(results)
    await run_press(adapter)

    kinds = [(event.kind, event.text) for event in events]
    assert kinds == [
        ("replace", "你"),
        ("replace", "你好，我是来自"),
        ("archive", FULL),
        ("final", FULL),
    ]


async def test_two_sentences_commit_separately_and_final_carries_everything() -> None:
    results = [
        result_generated("第一句话。", end=True),
        result_generated("第二句", end=False),
        result_generated("第二句话。", end=True),
    ]
    adapter, events, _vendor = build_adapter(results)
    await run_press(adapter)

    kinds = [(event.kind, event.text) for event in events]
    assert kinds == [
        ("archive", "第一句话。"),
        ("replace", "第二句"),
        ("archive", "第二句话。"),
        ("final", "第一句话。第二句话。"),
    ]


async def test_stop_sends_finish_task_after_the_audio() -> None:
    adapter, _events, vendor = build_adapter([])
    await run_press(adapter)

    frames = text_frames(vendor)
    assert frames[0]["header"]["action"] == "run-task"
    assert frames[-1]["header"]["action"] == "finish-task"
    assert frames[-1]["header"]["task_id"] == frames[0]["header"]["task_id"]
    binary = [frame for frame in vendor.client_frames if isinstance(frame, bytes)]
    assert len(binary) == -(-len(SAMPLE_PCM) // 3200)  # 3200-byte vendor frames
    assert b"".join(binary) == SAMPLE_PCM
    assert vendor.closed


async def test_task_failed_fails_the_channel_with_vendor_details() -> None:
    adapter, events, _vendor = build_adapter([failed_frame("ModelNotOpen", "model not open")])
    await adapter.start(ChannelCtx(session_id="p1a"))
    await adapter.feed(SAMPLE_PCM)
    with pytest.raises(AiUnavailable):
        await adapter.stop()
    with pytest.raises(AiUnavailable):
        await adapter.wait()
    assert "ModelNotOpen" in str(adapter.failure)
    assert events == []


async def test_no_audio_never_opens_a_connection() -> None:
    adapter, events, _vendor = build_adapter([])
    await adapter.start(ChannelCtx(session_id="p1a"))
    await adapter.stop()
    await adapter.wait()
    assert adapter.opened == {}
    assert events == []


async def test_connect_failure_is_reported_not_swallowed() -> None:
    events: list[TranscriptEvent] = []

    async def broken_open(url: str, headers: dict[str, str], open_timeout: float) -> FakeVendor:
        raise OSError("network unreachable")

    adapter = ParaformerRealtimeAdapter(
        api_key="sk-test", ws_url=WS_URL, on_event=events.append, connect=broken_open
    )
    await adapter.start(ChannelCtx(session_id="p1a"))
    await adapter.feed(SAMPLE_PCM)
    with pytest.raises(AiUnavailable):
        await adapter.stop()
    assert "network unreachable" in str(adapter.failure)
    assert events == []


async def test_vendor_never_finishes_reports_a_failure() -> None:
    adapter, events, _vendor = build_adapter([], finish=False, finish_timeout_seconds=0.1)
    await adapter.start(ChannelCtx(session_id="p1a"))
    await adapter.feed(SAMPLE_PCM)
    with pytest.raises(AiUnavailable):
        await adapter.stop()
    assert events == []


async def test_empty_text_partial_is_not_emitted() -> None:
    adapter, events, _vendor = build_adapter([result_generated("", end=False)])
    await run_press(adapter)
    assert events == []


async def test_missing_key_or_ws_url_is_a_config_error() -> None:
    with pytest.raises(MediaConfigError):
        ParaformerRealtimeAdapter(api_key="", ws_url=WS_URL, on_event=lambda event: None)
    with pytest.raises(MediaConfigError):
        ParaformerRealtimeAdapter(api_key="sk-test", ws_url="", on_event=lambda event: None)


async def test_realtime_ws_url_is_derived_from_the_batch_endpoint() -> None:
    assert derive_realtime_ws_url(BATCH_URL) == WS_URL
    assert derive_realtime_ws_url("") == ""


async def test_factory_builds_the_realtime_channel() -> None:
    from types import SimpleNamespace

    from better_resume.media.factory import build_transcription_channel

    media = MediaSettings(transcription_adapter="paraformer-rt", asr_url=BATCH_URL)
    settings = SimpleNamespace(media=media, dashscope_api_key="sk-test")
    channel = build_transcription_channel(settings, on_event=lambda event: None)  # type: ignore[arg-type]
    assert isinstance(channel, ParaformerRealtimeAdapter)
    assert channel.ws_url == WS_URL

    bare = SimpleNamespace(
        media=MediaSettings(transcription_adapter="paraformer-rt"), dashscope_api_key="sk-test"
    )
    with pytest.raises(MediaConfigError):
        build_transcription_channel(bare, on_event=lambda event: None)  # type: ignore[arg-type]
