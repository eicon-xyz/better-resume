"""Media endpoints: ticket-guarded transcription WebSocket and cached TTS."""

from __future__ import annotations

import asyncio
import contextlib
import json
import re
from typing import Any

import structlog
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import Response
from pydantic import BaseModel, Field

from ..ai_resilience import ResilientAiResilience, Stage
from ..identity import Principal, current_principal
from ..identity.tickets import WsTicketStore
from ..media import (
    ChannelCtx,
    EdgeTtsSynthesizer,
    TranscriptEvent,
    TtsCache,
    VoiceSpec,
    build_transcription_channel,
)
from ..settings import Settings

logger = structlog.get_logger("better_resume.http.media")

router = APIRouter(prefix="/api/v1/media", tags=["media"])

CLOSE_UNAUTHORIZED = 4401
CLOSE_ALREADY_ACTIVE = 4409
CLOSE_CHANNEL_FAILED = 4411

#: How long the server keeps trying to deliver the tail (archive/final) after stop.
FLUSH_BUDGET_SECONDS = 1.0

#: Cache digests are hex only: anything else cannot be a file we wrote (no path traversal).
_DIGEST = re.compile(r"^[0-9a-f]{64}$")


class TtsRequest(BaseModel):
    text: str = Field(min_length=1)
    voice: str | None = Field(default=None, max_length=64)
    rate: str | None = Field(default=None, max_length=16)


class TtsView(BaseModel):
    url: str
    mime_type: str
    cached: bool
    digest: str


def _synthesizer(request: Request) -> EdgeTtsSynthesizer:
    """Built once in lifespan so tests can swap the vendor engine."""
    return request.app.state.tts_synthesizer


@router.post("/tts", response_model=TtsView)
async def synthesize_speech(
    request: Request,
    payload: TtsRequest,
    principal: Principal = Depends(current_principal),  # noqa: B008
) -> TtsView:
    settings: Settings = request.app.state.settings
    if len(payload.text) > settings.media.tts_max_chars:
        raise HTTPException(
            status_code=422,
            detail=f"text is longer than {settings.media.tts_max_chars} characters",
        )

    synthesizer = _synthesizer(request)
    voice = VoiceSpec(voice=payload.voice or settings.media.tts_voice, rate=payload.rate)
    digest = synthesizer.cache_key(payload.text, voice)
    was_cached = synthesizer.cached(payload.text, voice) is not None

    # TTS is a vendor call like any other: the M3 chain gives it single flight, a breaker,
    # a deadline and a replay window keyed on the text digest.
    resilience: ResilientAiResilience = request.app.state.ai_resilience
    reference = await resilience.run(
        Stage.TTS,
        f"tts|{digest}",
        lambda: synthesizer.synthesize(payload.text, voice),
    )
    return TtsView(
        url=reference.url or f"/api/v1/media/tts/{digest}.mp3",
        mime_type=reference.mime_type,
        cached=was_cached,
        digest=digest,
    )


@router.get("/tts/{digest}.mp3")
async def get_speech(request: Request, digest: str) -> Response:
    settings: Settings = request.app.state.settings
    if not _DIGEST.match(digest):
        raise HTTPException(status_code=404, detail="tts audio not found")
    audio = TtsCache(settings.media.tts_storage_dir).read(digest)
    if audio is None:
        raise HTTPException(status_code=404, detail="tts audio not found")
    return Response(
        content=audio,
        media_type="audio/mpeg",
        headers={"Cache-Control": "private, max-age=86400"},
    )


@router.websocket("/transcribe")
async def transcribe(websocket: WebSocket, ticket: str | None = Query(default=None)) -> None:
    state = websocket.app.state
    settings: Settings = state.settings
    tickets: WsTicketStore = state.ws_ticket_store

    principal = await tickets.consume(ticket) if ticket else None
    if principal is None:
        await websocket.close(code=CLOSE_UNAUTHORIZED)
        return

    registry = state.transcription_registry
    if not registry.try_acquire(principal.user_id):
        await websocket.close(code=CLOSE_ALREADY_ACTIVE)
        return

    events: asyncio.Queue[TranscriptEvent] = asyncio.Queue()
    channel: Any = None
    failure: BaseException | None = None
    try:
        await websocket.accept()
        channel = build_transcription_channel(settings, on_event=lambda event: events.put(event))
        await channel.start(ChannelCtx(session_id=principal.user_id))

        sender = asyncio.create_task(_send_events(websocket, events), name="ws-media-send")
        receiver = asyncio.create_task(_pump_audio(websocket, channel), name="ws-media-recv")
        watcher = asyncio.create_task(channel.wait(), name="ws-media-channel")
        await asyncio.wait({sender, receiver, watcher}, return_when=asyncio.FIRST_COMPLETED)

        for task in (sender, receiver, watcher):
            task.cancel()
        for task in (sender, receiver, watcher):
            with contextlib.suppress(BaseException):
                await task
        if watcher.done() and not watcher.cancelled():
            failure = watcher.exception()

        # The client released the button (or vanished): freeze the channel first so the
        # tail (archive/final) exists, deliver it, and only then close the socket.
        with contextlib.suppress(BaseException):
            await channel.stop()
        await _flush(websocket, events)

        if failure is not None:
            logger.warning("media_channel_failed", error=str(failure))
            with contextlib.suppress(Exception):
                await websocket.close(code=CLOSE_CHANNEL_FAILED)
    except WebSocketDisconnect:
        logger.info("media_client_disconnected", user_id=principal.user_id)
    finally:
        if channel is not None:
            with contextlib.suppress(BaseException):
                await channel.stop()
        registry.release(principal.user_id)


async def _send_events(websocket: WebSocket, events: asyncio.Queue[TranscriptEvent]) -> None:
    while True:
        event = await events.get()
        await websocket.send_json(event.model_dump())


async def _flush(websocket: WebSocket, events: asyncio.Queue[TranscriptEvent]) -> None:
    """Best-effort delivery of the remaining frames (the socket may already be gone)."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + FLUSH_BUDGET_SECONDS
    while loop.time() < deadline:
        try:
            event = events.get_nowait()
        except asyncio.QueueEmpty:
            return
        with contextlib.suppress(Exception):
            await websocket.send_json(event.model_dump())


async def _pump_audio(websocket: WebSocket, channel: Any) -> None:
    while True:
        message = await websocket.receive()
        if message.get("type") == "websocket.disconnect":
            return
        data = message.get("bytes")
        if data:
            await channel.feed(data)
            continue
        text = message.get("text")
        if text:
            with contextlib.suppress(json.JSONDecodeError):
                if json.loads(text).get("type") == "stop":
                    return
