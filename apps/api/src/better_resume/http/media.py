"""Media endpoints: the ticket-guarded transcription WebSocket (TTS lands with T4)."""

from __future__ import annotations

import asyncio
import contextlib
import json
from typing import Any

import structlog
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from ..identity.tickets import WsTicketStore
from ..media import ChannelCtx, TranscriptEvent, build_transcription_channel
from ..settings import Settings

logger = structlog.get_logger("better_resume.http.media")

router = APIRouter(prefix="/api/v1/media", tags=["media"])

CLOSE_UNAUTHORIZED = 4401
CLOSE_ALREADY_ACTIVE = 4409
CLOSE_CHANNEL_FAILED = 4411

#: How long the server keeps trying to deliver the tail (archive/final) after stop.
FLUSH_BUDGET_SECONDS = 1.0


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

        # The client stopped talking (button released) or vanished: freeze the channel,
        # deliver whatever it still owes the client (archive/final), then close.
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
