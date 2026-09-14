"""Paraformer realtime channel: incremental ASR while the button is held (P1-A).

Wire contract verified against the live workspace endpoint (2026-09-15 preflight):

* wss://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/api-ws/v1/inference — the same workspace
  host as the batch endpoint, so no new credential or domain is needed (derive the wss://
  host from BR_MEDIA__ASR_URL unless BR_MEDIA__ASR_WS_URL says otherwise);
* `Authorization: Bearer <key>` is validated at the WS handshake (bad key = HTTP 401/403);
* run-task JSON -> task-started -> binary mono PCM frames (100 ms each) -> incremental
  result-generated events -> finish-task -> tail events -> task-finished.

Event mapping follows the xunfei streaming precedent (M4): a partial sentence rewrites the
live area (replace), a completed sentence is appended to the committed text (archive), and
the closing snapshot carries the whole run text (final). The M4 sentence pool is therefore
exercised for real — the batch adapter (qwen-asr) cannot trigger it.

No mid-stream reconnect in P1: audio lost while the vendor drops us cannot be replayed, so
a drop fails the channel (the WS endpoint closes 4411) instead of silently truncating text.
Reconnecting is what a new button press does.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import structlog

from ...ai_resilience import AiUnavailable, Stage
from ..models import ChannelCtx, TranscriptEvent
from .xunfei_ast import MediaConfigError

logger = structlog.get_logger("better_resume.media.paraformer_rt")

EventSink = Callable[[TranscriptEvent], Awaitable[None] | None]

DEFAULT_RT_MODEL = "paraformer-realtime-v2"
#: Audio bytes per vendor frame: 100 ms of 16 kHz mono s16le.
FRAME_BYTES = 3200
#: The fixed inference path on the workspace domain (vendor contract, 2026-09).
REALTIME_WS_PATH = "/api-ws/v1/inference"

#: Any websocket with send/recv/close — the real client or the fake in tests.
Connection = Any
ConnectFn = Callable[[str, dict[str, str], float], Awaitable[Connection]]


def derive_realtime_ws_url(batch_endpoint: str) -> str:
    """The realtime WS shares the workspace host with the batch endpoint, so an existing
    BR_MEDIA__ASR_URL is enough: same host, wss scheme, fixed inference path."""
    if not batch_endpoint or "//" not in batch_endpoint:
        return ""
    host = batch_endpoint.split("//", 1)[1].split("/", 1)[0]
    if not host:
        return ""
    return f"wss://{host}{REALTIME_WS_PATH}"


async def open_connection(ws_url: str, headers: dict[str, str], open_timeout: float) -> Connection:
    """The real vendor connection; tests swap `connect=` instead of this.

    websockets >= 14 renamed extra_headers and grew a proxy argument, and a malformed
    NO_PROXY on this machine must not take the channel down (P20) — hence the fallbacks.
    """
    import websockets

    attempts: tuple[dict[str, Any], ...] = (
        {"additional_headers": headers, "open_timeout": open_timeout, "proxy": None},
        {"additional_headers": headers, "open_timeout": open_timeout},
        {"extra_headers": headers, "open_timeout": open_timeout},
    )
    for kwargs in attempts:
        try:
            return await websockets.connect(ws_url, **kwargs)
        except TypeError:
            continue
    raise MediaConfigError("no compatible websockets.connect signature on this host")


def parse_event(frame: str) -> tuple[str, str, bool]:
    """(event, sentence_text, sentence_end) for a server frame; unparsable -> ("?", "", False)."""
    try:
        payload = json.loads(frame)
    except json.JSONDecodeError:
        return "?", "", False
    header = payload.get("header") or {}
    sentence = (payload.get("payload", {}).get("output", {}) or {}).get("sentence") or {}
    text = sentence.get("text") if isinstance(sentence.get("text"), str) else ""
    end = bool(sentence.get("sentence_end", False))
    return str(header.get("event", "?")), text.strip(), end


class ParaformerRealtimeAdapter:
    """TranscriptionChannel for the Bailian realtime recognition websocket."""

    def __init__(
        self,
        *,
        api_key: str,
        ws_url: str,
        on_event: EventSink,
        model: str = DEFAULT_RT_MODEL,
        sample_rate: int = 16000,
        timeout_seconds: float = 30.0,
        finish_timeout_seconds: float = 5.0,
        connect: ConnectFn | None = None,
    ) -> None:
        if not api_key:
            raise MediaConfigError("paraformer-rt needs BR_DASHSCOPE_API_KEY")
        if not ws_url:
            raise MediaConfigError(
                "paraformer-rt needs BR_MEDIA__ASR_WS_URL (or BR_MEDIA__ASR_URL to derive it)"
            )
        self.api_key = api_key
        self.ws_url = ws_url
        self._on_event = on_event
        self._model = model
        self._sample_rate = sample_rate
        self._timeout = timeout_seconds
        self._finish_timeout = finish_timeout_seconds
        self._connect: ConnectFn = connect or open_connection
        self._buffer = bytearray()
        self._session: asyncio.Task[None] | None = None
        self._started = False
        self._stopped = False
        self._finished: asyncio.Event | None = None
        self._task_id = ""
        self._sentences: list[str] = []
        self._live = ""
        #: Read by the WS endpoint after stop() so a failed run closes the socket as 4411.
        self.failure: BaseException | None = None

    # ---- TranscriptionChannel -----------------------------------------------------

    async def start(self, ctx: ChannelCtx) -> None:
        self._buffer.clear()
        self._sentences = []
        self._live = ""
        self._started = True
        self._stopped = False
        self.failure = None
        self._finished = asyncio.Event()
        self._task_id = uuid.uuid4().hex
        self._sample_rate = ctx.sample_rate or self._sample_rate

    async def feed(self, pcm: bytes) -> None:
        if not self._started or self._stopped or not pcm:
            return
        self._buffer.extend(pcm)
        # Lazy connect: the first audio opens the vendor session, so pressing the button
        # without saying anything never costs a connection.
        if self._session is None:
            self._session = asyncio.create_task(self._run_session(), name="paraformer-rt-session")

    async def stop(self) -> None:
        """Ask the vendor to flush, deliver the closing snapshot, then surface failures."""
        if self._stopped:
            return
        self._stopped = True
        if self._session is not None:
            await self._session
        if self._finished is not None:
            self._finished.set()
        if self.failure is not None:
            raise self.failure

    async def wait(self) -> None:
        """Block until the run ends (vendor finished or failed); raise the failure."""
        if self._finished is not None:
            await self._finished.wait()
        if self.failure is not None:
            raise self.failure

    # ---- vendor session ------------------------------------------------------------

    async def _run_session(self) -> None:
        loop = asyncio.get_running_loop()
        connection: Connection | None = None
        try:
            connection = await self._connect(self.ws_url, self._headers(), self._timeout)
            await connection.send(self._run_task_frame())
            started = False
            while not started:
                frame = await asyncio.wait_for(connection.recv(), timeout=self._timeout)
                event, _text, _end = parse_event(frame)
                if event == "task-started":
                    started = True
                elif event == "task-failed":
                    raise self._task_failed(frame)
            logger.info(
                "paraformer_rt_started",
                task_id=self._task_id,
                model=self._model,
                sample_rate=self._sample_rate,
            )
            finish_sent = False
            finish_deadline = 0.0
            last_message_at = loop.time()
            while True:
                if self._buffer:
                    chunk = bytes(self._buffer[:FRAME_BYTES])
                    del self._buffer[: len(chunk)]
                    await connection.send(chunk)
                    continue
                if not finish_sent and self._stopped:
                    await connection.send(self._finish_task_frame())
                    finish_sent = True
                    finish_deadline = loop.time() + self._finish_timeout
                try:
                    frame = await asyncio.wait_for(connection.recv(), timeout=0.02)
                except TimeoutError:
                    if finish_sent and loop.time() > finish_deadline:
                        raise AiUnavailable(
                            "paraformer-rt: vendor never finished the task",
                            stage=Stage.EXTRACTION,
                        ) from None
                    if not finish_sent and loop.time() - last_message_at > self._timeout:
                        raise AiUnavailable(
                            "paraformer-rt: vendor went silent mid-run",
                            stage=Stage.EXTRACTION,
                        ) from None
                    continue
                last_message_at = loop.time()
                event, text, end = parse_event(frame)
                if event == "result-generated":
                    await self._on_result(text, end)
                elif event == "task-failed":
                    raise self._task_failed(frame)
                elif event == "task-finished":
                    break
        except AiUnavailable as exc:
            self._fail(exc)
            return
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - vendor connection failures are expected
            self._fail(
                AiUnavailable(f"paraformer-rt connection failed: {exc}", stage=Stage.EXTRACTION)
            )
            return
        finally:
            if connection is not None:
                with contextlib.suppress(Exception):
                    await connection.close()
        full = "".join(self._sentences) + self._live
        if full:
            await self._emit(TranscriptEvent(kind="final", text=full))
        else:
            logger.warning("paraformer_rt_no_speech", session=self._task_id)

    async def _on_result(self, text: str, end: bool) -> None:
        if end:
            if text:
                self._sentences.append(text)
                await self._emit(TranscriptEvent(kind="archive", text=text))
            self._live = ""
            return
        if text and text != self._live:
            self._live = text
            await self._emit(TranscriptEvent(kind="replace", text=text))

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "user-agent": "better-resume/paraformer-rt",
        }

    def _run_task_frame(self) -> str:
        return json.dumps(
            {
                "header": {"action": "run-task", "task_id": self._task_id, "streaming": "duplex"},
                "payload": {
                    "model": self._model,
                    "task_group": "audio",
                    "task": "asr",
                    "function": "recognition",
                    "parameters": {"format": "pcm", "sample_rate": self._sample_rate},
                    "input": {},
                },
            }
        )

    def _finish_task_frame(self) -> str:
        return json.dumps(
            {
                "header": {
                    "action": "finish-task",
                    "task_id": self._task_id,
                    "streaming": "duplex",
                },
                "payload": {"input": {}},
            }
        )

    @staticmethod
    def _task_failed(frame: str) -> AiUnavailable:
        try:
            header = json.loads(frame).get("header", {})
        except json.JSONDecodeError:
            header = {}
        return AiUnavailable(
            f"paraformer-rt task failed: {header.get('error_code')}: {header.get('error_message')}",
            stage=Stage.EXTRACTION,
        )

    def _fail(self, exc: AiUnavailable) -> None:
        self.failure = exc
        logger.warning("paraformer_rt_failed", error=str(exc))
        if self._finished is not None:
            self._finished.set()

    async def _emit(self, event: TranscriptEvent) -> None:
        result = self._on_event(event)
        if hasattr(result, "__await__"):
            await result  # type: ignore[misc]
