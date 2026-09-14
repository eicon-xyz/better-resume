"""Qwen-Audio-3.0-ASR-Flash channel: buffer while the button is held, transcribe on release.

Why a buffer: the vendor takes a whole audio clip and answers once (batch), so unlike the
xunfei AST adapter there are no incremental packets to merge. What the client sees is a single
"final" event a second or two after the user releases the button, and the M4 sentence pool
(which exists to merge *incremental* vendor packets) is not exercised by this adapter. That
trade-off is recorded in docs/tickets/v1-verification/V3-speech-to-text-real-machine.md.

Wire format verified against the live endpoint (2026-09-14):
A "data:audio/wav;base64,..." URI is required; a bare base64 string is rejected with HTTP 500.
"""

from __future__ import annotations

import array
import asyncio
import base64
import io
import wave
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import structlog

from ..models import ChannelCtx, TranscriptEvent
from .xunfei_ast import MediaConfigError

logger = structlog.get_logger("better_resume.media.qwen_asr")

EventSink = Callable[[TranscriptEvent], Awaitable[None] | None]

DEFAULT_ASR_MODEL = "qwen-audio-3.0-asr-flash"
#: Below ~0.25 s the vendor answers 400 with an empty body, so do not even ask.
MIN_CLIP_BYTES = 8000
#: int16 peak below this is treated as "the microphone sent silence" (the vendor 400s on it).
SILENCE_PEAK = 200
#: The MaaS workspace endpoint is account specific, so it has no sensible default.
DEFAULT_ASR_URL = ""


def pcm_peak(pcm: bytes) -> int:
    """Loudest sample in the clip: 0 means the client sent silence."""
    samples = array.array("h")
    samples.frombytes(pcm[: len(pcm) // 2 * 2])
    return max((abs(value) for value in samples), default=0)


def pcm_to_wav(pcm: bytes, *, sample_rate: int = 16000, channels: int = 1, bits: int = 16) -> bytes:
    """Wrap raw little-endian PCM in a minimal WAV container (the vendor wants a real file)."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(bits // 8)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm)
    return buffer.getvalue()


def build_client(timeout_seconds: float) -> httpx.AsyncClient:
    """Same defensive construction as the LLM adapter: a malformed NO_PROXY (WSL exports
    bare IPv6 entries) makes httpx raise while it parses the environment, and that must not
    take the whole channel down."""
    timeout = httpx.Timeout(timeout_seconds)
    try:
        return httpx.AsyncClient(timeout=timeout)
    except (httpx.InvalidURL, ValueError):
        logger.warning("qwen_asr_proxy_env_ignored", reason="malformed NO_PROXY")
        return httpx.AsyncClient(timeout=timeout, trust_env=False)


def to_data_uri(wav: bytes) -> str:
    return "data:audio/wav;base64," + base64.b64encode(wav).decode("ascii")


def parse_text(payload: dict[str, Any]) -> str:
    """The transcript sits at the top level; "output" repeats it. Empty means silence."""
    for source in (payload, payload.get("output") or {}):
        text = source.get("text") if isinstance(source, dict) else None
        if isinstance(text, str) and text.strip():
            return text.strip()
    sentence = payload.get("sentence") or (payload.get("output") or {}).get("sentence") or {}
    text = sentence.get("text") if isinstance(sentence, dict) else None
    return text.strip() if isinstance(text, str) else ""


class QwenAsrFlashAdapter:
    """TranscriptionChannel for a batch ASR endpoint (one request per release)."""

    def __init__(
        self,
        *,
        api_key: str,
        endpoint: str,
        on_event: EventSink,
        model: str = DEFAULT_ASR_MODEL,
        sample_rate: int = 16000,
        timeout_seconds: float = 30.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key:
            raise MediaConfigError("qwen-asr needs BR_DASHSCOPE_API_KEY")
        if not endpoint:
            raise MediaConfigError("qwen-asr needs BR_MEDIA__ASR_URL (the MaaS workspace endpoint)")
        self._api_key = api_key
        self._endpoint = endpoint
        self._on_event = on_event
        self._model = model
        self._sample_rate = sample_rate
        self._timeout = timeout_seconds
        self._client = client
        self._owns_client = client is None
        self._buffer = bytearray()
        self._started = False
        self._stopped = False
        self._finished: asyncio.Event | None = None
        #: Read by the WS endpoint after stop() so a failed transcription closes the socket.
        self.failure: BaseException | None = None
        self.last_request_bytes = 0

    # ---- TranscriptionChannel -----------------------------------------------------

    async def start(self, ctx: ChannelCtx) -> None:
        self._buffer.clear()
        self._started = True
        self._stopped = False
        self.failure = None
        self._finished = asyncio.Event()
        self._sample_rate = ctx.sample_rate or self._sample_rate

    async def feed(self, pcm: bytes) -> None:
        if not self._started or self._stopped:
            return
        self._buffer.extend(pcm)

    async def stop(self) -> None:
        """Transcribe whatever was buffered and emit the single final event."""
        if self._stopped:
            return
        self._stopped = True
        try:
            if self._buffer:
                pcm = bytes(self._buffer)
                seconds = len(pcm) / (self._sample_rate * 2)
                peak = pcm_peak(pcm)
                logger.info("qwen_asr_clip", bytes=len(pcm), seconds=round(seconds, 2), peak=peak)
                if len(pcm) < MIN_CLIP_BYTES or peak < SILENCE_PEAK:
                    # Nothing to recognise: skip the vendor call (it answers 400 for this) and
                    # end cleanly. Logged loudly because it usually means the client sent
                    # silence, which is a capture problem, not a transcription problem.
                    logger.warning(
                        "qwen_asr_no_speech",
                        bytes=len(pcm),
                        seconds=round(seconds, 2),
                        peak=peak,
                    )
                    return
                text = await self._transcribe(pcm)
                if text:
                    await self._emit(TranscriptEvent(kind="final", text=text))
        except Exception as exc:  # noqa: BLE001 - the endpoint surfaces this via .failure
            self.failure = exc
            logger.warning("qwen_asr_failed", error=f"{type(exc).__name__}: {exc}")
            raise
        finally:
            # wait() must not return before the transcription finished: the WS endpoint
            # treats a completed watcher as "the channel ended" and closes the socket.
            if self._finished is not None:
                self._finished.set()

    async def wait(self) -> None:
        """Block until stop() finished, then raise the failure (if any)."""
        if self._finished is not None:
            await self._finished.wait()
        if self.failure is not None:
            raise self.failure

    # ---- internals ----------------------------------------------------------------

    async def _transcribe(self, pcm: bytes) -> str:
        wav = pcm_to_wav(pcm, sample_rate=self._sample_rate)
        body = {
            "model": self._model,
            "input": {
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_audio", "input_audio": {"data": to_data_uri(wav)}}
                        ],
                    }
                ]
            },
            "parameters": {"format": "wav", "sample_rate": str(self._sample_rate)},
        }
        self.last_request_bytes = len(wav)
        client = self._client or build_client(self._timeout)
        try:
            response = await client.post(
                self._endpoint,
                json=body,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                    "X-DashScope-SSE": "disable",
                },
            )
        except httpx.HTTPError as exc:
            raise MediaConfigError(f"qwen-asr request failed: {exc}") from exc
        finally:
            if self._owns_client:
                await client.aclose()
        if response.status_code >= 400:
            body = response.text[:200]
            hint = ""
            if response.status_code == 400 and body.strip() in ("", "{}"):
                hint = " (empty 400: the vendor rejected the audio, usually too short or silent)"
            raise MediaConfigError(f"qwen-asr returned {response.status_code}: {body}{hint}")
        return parse_text(response.json())

    async def _emit(self, event: TranscriptEvent) -> None:
        result = self._on_event(event)
        if hasattr(result, "__await__"):
            await result  # type: ignore[misc]
