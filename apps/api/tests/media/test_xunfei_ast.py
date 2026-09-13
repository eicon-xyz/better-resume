"""M4-T2: xunfei AST adapter — signing, pacing, parsing, failures, reconnect.

The vendor boundary is faked with a real local WebSocket server; nothing inside the
adapter is patched, so the frames, the JSON parsing and the assembler wiring are all real.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

import pytest
from websockets.asyncio.server import serve

from better_resume.ai_resilience import AiUnavailable, ManualClock
from better_resume.media import ChannelCtx, TranscriptEvent
from better_resume.media.adapters import (
    MediaConfigError,
    ScriptedTranscriptionChannel,
    XunfeiAstAdapter,
    XunfeiCredentials,
    build_signed_url,
    parse_result_payload,
)

CREDS = XunfeiCredentials(app_id="app-1", access_key_id="key-1", access_key_secret="secret-1")
CTX = ChannelCtx(session_id="session-1")


def ast_payload(
    text: str,
    *,
    seg_id: int = 1,
    pgs: str | None = "apd",
    bg: int = 0,
    ed: int = 1000,
    final: bool = False,
) -> dict:
    payload: dict = {
        "seg_id": seg_id,
        "type": 0,
        "ls": final,
        "cn": {"st": {"bg": str(bg), "ed": str(ed), "rt": [{"ws": [{"cw": [{"w": text}]}]}]}},
    }
    if pgs is not None:
        payload["pgs"] = pgs
    return payload


async def wait_for(predicate, budget: float = 3.0) -> bool:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + budget
    while loop.time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.01)
    return False


class FakeAstServer:
    """Minimal vendor stand-in: sends a script, records frames and pings."""

    def __init__(self, *, script: list[dict] | None = None, drop_connections: int = 0) -> None:
        self.script = list(script or [])
        self.drop_connections = drop_connections
        self.connections = 0
        self.paths: list[str] = []
        self.frames: list[bytes] = []
        self.texts: list[str] = []
        self.url = ""
        self._server = None

    async def __aenter__(self) -> FakeAstServer:
        self._server = await serve(self._handler, "127.0.0.1", 0)
        port = self._server.sockets[0].getsockname()[1]
        self.url = f"ws://127.0.0.1:{port}/ast/communicate/v1"
        return self

    async def __aexit__(self, *exc: object) -> bool:
        self._server.close()
        await self._server.wait_closed()
        return False

    async def _handler(self, ws) -> None:
        self.connections += 1
        self.paths.append(ws.request.path)
        if self.connections <= self.drop_connections:
            await ws.close(code=1011, reason="injected drop")
            return
        for item in self.script:
            await ws.send(json.dumps(item))
            await asyncio.sleep(0.01)
        try:
            async for message in ws:
                if isinstance(message, bytes):
                    self.frames.append(message)
                else:
                    self.texts.append(message)
        except Exception:  # noqa: BLE001
            # The client may vanish mid-test; that is exactly what some cases assert.
            return


def collector() -> tuple[list[TranscriptEvent], object]:
    events: list[TranscriptEvent] = []

    async def on_event(event: TranscriptEvent) -> None:
        events.append(event)

    return events, on_event


def test_signed_url_is_deterministic_and_complete() -> None:
    stamp = datetime(2026, 9, 14, 12, 0, 0, tzinfo=UTC)

    url = build_signed_url(CREDS, now=stamp)

    assert url == build_signed_url(CREDS, now=stamp)
    assert "appId=app-1" in url
    assert "accessKeyId=key-1" in url
    assert "audio_encode=pcm_s16le" in url
    assert "samplerate=16000" in url
    assert "lang=autodialect" in url
    assert "signature=" in url
    assert "secret-1" not in url

    other = build_signed_url(
        XunfeiCredentials(app_id="app-1", access_key_id="key-1", access_key_secret="secret-2"),
        now=stamp,
    )
    assert other != url


def test_incomplete_credentials_are_rejected_loudly() -> None:
    with pytest.raises(MediaConfigError, match="access_key_secret"):
        XunfeiCredentials(app_id="app", access_key_id="key", access_key_secret="").require()
    with pytest.raises(MediaConfigError):
        build_signed_url(XunfeiCredentials(app_id="", access_key_id="", access_key_secret=""))


def test_parser_reads_the_nested_shape_and_tolerates_noise() -> None:
    packet = parse_result_payload(ast_payload("你好", final=True))

    assert packet is not None
    assert packet.text == "你好"
    assert packet.seg_id == 1
    assert packet.final is True
    assert packet.bg == 0 and packet.ed == 1000

    assert parse_result_payload({"cn": {}}) is None
    assert parse_result_payload({"action": "started"}) is None
    assert parse_result_payload(ast_payload("x", pgs="weird")).pgs is None  # type: ignore[union-attr]

    with pytest.raises(AiUnavailable, match="10165"):
        parse_result_payload({"code": "10165", "desc": "invalid app id"})


async def test_handshake_uses_the_signed_query() -> None:
    events, on_event = collector()
    async with FakeAstServer() as server:
        adapter = XunfeiAstAdapter(credentials=CREDS, on_event=on_event, ws_url=server.url)
        await adapter.start(CTX)
        assert await wait_for(lambda: server.connections == 1)
        await adapter.stop()

    assert "signature=" in server.paths[0]
    assert "appId=app-1" in server.paths[0]
    assert events == []  # nothing was spoken


async def test_frames_are_sliced_at_1280_bytes_and_paced() -> None:
    events, on_event = collector()
    clock = ManualClock()
    async with FakeAstServer() as server:
        adapter = XunfeiAstAdapter(
            credentials=CREDS, on_event=on_event, ws_url=server.url, clock=clock
        )
        await adapter.start(CTX)
        assert await wait_for(lambda: server.connections == 1)

        await adapter.feed(b"\x00" * 3200)
        for _ in range(5):
            clock.advance(0.04)
            await asyncio.sleep(0.02)

        assert [len(frame) for frame in server.frames[:3]] == [1280, 1280, 640]
        await adapter.stop()


async def test_results_become_replace_and_archive_events() -> None:
    events, on_event = collector()
    script = [ast_payload("你好"), ast_payload("你好。", final=True)]
    async with FakeAstServer(script=script) as server:
        adapter = XunfeiAstAdapter(credentials=CREDS, on_event=on_event, ws_url=server.url)
        await adapter.start(CTX)
        assert await wait_for(lambda: len(events) >= 2)

        await adapter.stop()

    assert [(event.kind, event.text) for event in events] == [
        ("replace", "你好"),
        ("archive", "你好。"),
        ("final", "你好。"),
    ]


async def test_vendor_error_frame_surfaces_as_unavailable() -> None:
    events, on_event = collector()
    script = [{"code": "10165", "desc": "invalid app id"}]
    async with FakeAstServer(script=script) as server:
        adapter = XunfeiAstAdapter(credentials=CREDS, on_event=on_event, ws_url=server.url)
        await adapter.start(CTX)

        assert await wait_for(lambda: adapter.failure is not None)
        with pytest.raises(AiUnavailable):
            await adapter.wait()
        await adapter.stop()


async def test_reconnect_then_give_up() -> None:
    events, on_event = collector()
    async with FakeAstServer(drop_connections=2) as server:
        adapter = XunfeiAstAdapter(
            credentials=CREDS, on_event=on_event, ws_url=server.url, max_reconnects=1
        )
        await adapter.start(CTX)

        assert await wait_for(lambda: adapter.failure is not None)
        assert server.connections == 2  # one retry, then it stopped
        with pytest.raises(AiUnavailable, match="connection failed"):
            await adapter.wait()
        await adapter.stop()


async def test_stop_is_idempotent_and_emits_one_final() -> None:
    events, on_event = collector()
    async with FakeAstServer(script=[ast_payload("收尾")]) as server:
        adapter = XunfeiAstAdapter(credentials=CREDS, on_event=on_event, ws_url=server.url)
        await adapter.start(CTX)
        assert await wait_for(lambda: len(events) >= 1)

        await adapter.stop()
        await adapter.stop()

    assert [event.kind for event in events].count("final") == 1
    assert events[-1].text == "收尾"
    assert adapter._tasks == []  # noqa: SLF001 - asserted on purpose: no dangling tasks


async def test_scripted_channel_drives_the_same_event_stream() -> None:
    events, on_event = collector()
    channel = ScriptedTranscriptionChannel(on_event=on_event)

    await channel.start(CTX)
    await channel.feed(b"\x00" * 1280)
    await channel.feed(b"\x00" * 1280)
    first_batch = list(events)
    await channel.feed(b"\x00" * 1280)
    await channel.stop()
    await channel.stop()

    assert [event.kind for event in first_batch] == ["replace", "replace"]
    assert events[-1].kind == "final"
    assert events[-1].text == "我负责了订单写入链路的重构。"
    assert channel.stopped_calls == 2
