"""Xunfei AST adapter: the only place that knows about pgs/rg/signatures (§4.4).

Contract notes (kept honest):
* the URL signing order below follows the analysis document; **the vendor's acceptance of
  our signature is only verified on the real service (T10)**;
* frames are pushed at 1280 bytes / 40 ms, matching the old implementation;
* vendor errors become the M3 taxonomy (AiUnavailable) so callers keep one failure model;
* events leave through on_event as normalized TranscriptEvent(replace|archive|final).
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import hmac
import inspect
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import format_datetime
from typing import Any
from urllib.parse import quote

import structlog
from websockets.asyncio.client import connect

from ...ai_resilience import AiUnavailable, Stage
from ..assembler import AstTranscriptionAssembler
from ..models import AstPacket, ChannelCtx, PgsKind, TranscriptEvent, TranscriptUpdate

logger = structlog.get_logger("better_resume.media.xunfei")

DEFAULT_WS_URL = "wss://office-api-ast-dx.iflyaisol.com/ast/communicate/v1"
FRAME_BYTES = 1280
FRAME_MILLIS = 40
_TERMINAL_CODES = {"10165", "10160", "10161", "10163", "10170"}


class MediaConfigError(RuntimeError):
    """Missing or unusable media configuration (never silently degrade to fake data)."""


@dataclass(frozen=True)
class XunfeiCredentials:
    app_id: str
    access_key_id: str
    access_key_secret: str

    def require(self) -> XunfeiCredentials:
        missing = [
            name
            for name, value in (
                ("app_id", self.app_id),
                ("access_key_id", self.access_key_id),
                ("access_key_secret", self.access_key_secret),
            )
            if not value
        ]
        if missing:
            raise MediaConfigError("xunfei AST credentials are incomplete: " + ", ".join(missing))
        return self


def build_signed_url(
    credentials: XunfeiCredentials,
    *,
    ws_url: str = DEFAULT_WS_URL,
    sample_rate: int = 16000,
    language: str = "autodialect",
    now: datetime | None = None,
) -> str:
    """Signed handshake URL: sorted query string + HmacSHA1 + base64."""
    credentials.require()
    stamp = now or datetime.now(UTC)
    params = {
        "accessKeyId": credentials.access_key_id,
        "appId": credentials.app_id,
        "audio_encode": "pcm_s16le",
        "date": format_datetime(stamp.astimezone(UTC), usegmt=True),
        "lang": language,
        "samplerate": str(sample_rate),
    }
    base = "&".join(f"{key}={quote(str(value), safe='')}" for key, value in sorted(params.items()))
    digest = hmac.new(
        credentials.access_key_secret.encode("utf-8"), base.encode("utf-8"), hashlib.sha1
    ).digest()
    signature = base64.b64encode(digest).decode("ascii")
    return f"{ws_url}?{base}&signature={quote(signature, safe='')}"


def parse_result_payload(payload: dict[str, Any]) -> AstPacket | None:
    """Tolerant reader for the nested cn.st.rt[].ws[].cw[].w shape."""
    code = payload.get("code")
    if code not in (None, 0, "0"):
        message = str(payload.get("desc") or payload.get("message") or code)
        raise AiUnavailable(f"xunfei AST error {code}: {message}", stage=Stage.EXTRACTION)
    if payload.get("action") == "started":
        return None

    section = (payload.get("cn") or {}).get("st") or {}
    text = "".join(
        word.get("w", "")
        for rt in section.get("rt") or []
        for ws in rt.get("ws") or []
        for word in ws.get("cw") or []
    )
    if not text:
        return None

    raw_pgs = payload.get("pgs")
    pgs = PgsKind(raw_pgs) if raw_pgs in ("apd", "rpl") else None
    raw_rg = payload.get("rg")
    rg = (int(raw_rg[0]), int(raw_rg[1])) if isinstance(raw_rg, list) and len(raw_rg) == 2 else None
    final = bool(payload.get("final") or payload.get("ls"))
    return AstPacket(
        text=text,
        seg_id=int(payload["seg_id"]) if payload.get("seg_id") is not None else None,
        pgs=pgs,
        rg=rg,
        bg=int(section["bg"]) if section.get("bg") is not None else None,
        ed=int(section["ed"]) if section.get("ed") is not None else None,
        final=final,
    )


EventSink = Callable[[TranscriptEvent], Awaitable[None] | None]


class XunfeiAstAdapter:
    """TranscriptionChannel over the vendor WebSocket (signing, pacing, parsing, reconnect)."""

    def __init__(
        self,
        *,
        credentials: XunfeiCredentials,
        on_event: EventSink,
        ws_url: str = DEFAULT_WS_URL,
        sample_rate: int = 16000,
        language: str = "autodialect",
        frame_bytes: int = FRAME_BYTES,
        frame_millis: int = FRAME_MILLIS,
        max_reconnects: int = 1,
        clock: object | None = None,
    ) -> None:
        self._credentials = credentials.require()
        self._on_event = on_event
        self._ws_url = ws_url
        self._sample_rate = sample_rate
        self._language = language
        self._frame_bytes = frame_bytes
        self._frame_seconds = frame_millis / 1000
        self._max_reconnects = max_reconnects
        self._clock = clock
        self._buffer = bytearray()
        self._assembler = AstTranscriptionAssembler()
        self._committed_seen = ""
        self._tasks: list[asyncio.Task[None]] = []
        self._receive_task: asyncio.Task[None] | None = None
        self._connection: Any = None
        self._stopped = False
        self.reconnects = 0
        #: Set by the receive loop so callers (the WS endpoint) can surface the failure.
        self.failure: BaseException | None = None

    # ---- TranscriptionChannel ---------------------------------------------------

    async def start(self, ctx: ChannelCtx) -> None:
        self._stopped = False
        self._ping_seconds = max(5.0, self._frame_seconds * 10)
        self._tasks.append(asyncio.create_task(self._pump(), name="xunfei-pump"))
        self._tasks.append(asyncio.create_task(self._pump_pings(), name="xunfei-ping"))
        self._receive_task = asyncio.create_task(self._receive_loop(ctx), name="xunfei-recv")
        self._tasks.append(self._receive_task)

    async def feed(self, pcm: bytes) -> None:
        if self._stopped:
            return
        self._buffer.extend(pcm)

    async def wait(self) -> None:
        """Block until the channel ends, then raise its failure (if any)."""
        # Only the receive loop ends by itself; the pump/ping loops are cancelled by stop().
        task = self._receive_task
        if task is not None and task is not asyncio.current_task():
            await asyncio.gather(task, return_exceptions=True)
        if self.failure is not None:
            raise self.failure

    async def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with contextlib.suppress(BaseException):
                await task
        self._tasks.clear()
        await self._close_connection()
        snapshot = self._assembler.snapshot()
        if snapshot.display:
            await self._emit(TranscriptEvent(kind="final", text=snapshot.display))

    # ---- internals --------------------------------------------------------------

    async def _pump(self) -> None:
        while True:
            await self._sleep(self._frame_seconds)
            if not self._buffer or self._connection is None:
                continue
            frame = bytes(self._buffer[: self._frame_bytes])
            del self._buffer[: self._frame_bytes]
            with contextlib.suppress(Exception):
                await self._connection.send(frame)

    async def _pump_pings(self) -> None:
        while True:
            await self._sleep(self._ping_seconds)
            if self._connection is None:
                continue
            with contextlib.suppress(Exception):
                await self._connection.send(json.dumps({"type": "ping"}))

    async def _receive_loop(self, ctx: ChannelCtx) -> None:
        attempt = 0
        while not self._stopped:
            reason = "unknown"
            try:
                url = build_signed_url(
                    self._credentials,
                    ws_url=self._ws_url,
                    sample_rate=self._sample_rate,
                    language=self._language,
                )
                async with connect(url, max_size=None, open_timeout=10) as connection:
                    # NOTE: the reconnect budget is per start(), never reset here:
                    # resetting it on every successful connect turns the retry loop
                    # into an infinite one whenever the vendor keeps dropping us.
                    self._connection = connection
                    async for message in connection:
                        if isinstance(message, bytes):
                            continue
                        await self._handle_message(message)
                # Falling out of the loop means the vendor closed cleanly: still a drop.
                reason = "vendor closed the connection"
            except asyncio.CancelledError:
                raise
            except AiUnavailable as exc:
                self.failure = exc
                return
            except Exception as exc:  # noqa: BLE001 - vendor connection failures are expected
                reason = f"{type(exc).__name__}: {exc}"
            finally:
                self._connection = None

            if self._stopped:
                return
            attempt += 1
            if attempt > self._max_reconnects:
                self.failure = AiUnavailable(
                    f"xunfei AST connection failed: {reason}", stage=Stage.EXTRACTION
                )
                return
            self.reconnects += 1
            logger.warning("xunfei_reconnecting", attempt=attempt, reason=reason)
            await self._sleep(0.5)

    async def _handle_message(self, message: str) -> None:
        try:
            payload = json.loads(message)
        except json.JSONDecodeError:
            logger.warning("xunfei_unparsable_frame", sample=message[:80])
            return
        packet = parse_result_payload(payload)
        if packet is None:
            return
        update = self._assembler.apply(packet)
        await self._emit_update(update)

    async def _emit_update(self, update: TranscriptUpdate) -> None:
        # Protocol: non-final packets rewrite the live area; a final packet only appends
        # the newly committed sentence (clients clear their live area on archive).
        if update.final_packet:
            if len(update.committed) > len(self._committed_seen):
                newly = update.committed[len(self._committed_seen) :]
                self._committed_seen = update.committed
                await self._emit(TranscriptEvent(kind="archive", text=newly))
            return
        if update.changed:
            await self._emit(TranscriptEvent(kind="replace", text=update.live))

    async def _emit(self, event: TranscriptEvent) -> None:
        result = self._on_event(event)
        if inspect.isawaitable(result):
            await result

    async def _close_connection(self) -> None:
        connection, self._connection = self._connection, None
        if connection is None:
            return
        with contextlib.suppress(Exception):
            await connection.close()

    async def _sleep(self, seconds: float) -> None:
        if self._clock is not None:
            await self._clock.sleep(seconds)  # type: ignore[attr-defined]
        else:
            await asyncio.sleep(seconds)
