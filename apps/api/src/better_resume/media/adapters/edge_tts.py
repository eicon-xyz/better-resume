"""edge-tts adapter: short-text synthesis with an injectable engine (vendor is a seam).

The engine callable is the system boundary: production passes edge_tts.Communicate, tests
pass a fake, so no test ever talks to Microsoft. Failures map onto the M3 taxonomy.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import structlog

from ...ai_resilience import AiUnavailable
from ..models import AudioRef, VoiceSpec
from ..tts_cache import TtsCache

logger = structlog.get_logger("better_resume.media.tts")

Engine = Callable[[str, str, str | None], Awaitable[bytes]]

DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"


async def _edge_engine(text: str, voice: str, rate: str | None) -> bytes:
    import edge_tts  # imported lazily: the package is only needed when TTS is used

    communicate = edge_tts.Communicate(text, voice, rate=rate)
    audio = bytearray()
    async for chunk in communicate.stream():
        if chunk.get("type") == "audio":
            audio.extend(chunk.get("data", b""))
    return bytes(audio)


class EdgeTtsSynthesizer:
    """TtsSynthesizer implementation backed by the on-disk cache."""

    def __init__(
        self,
        *,
        cache: TtsCache,
        engine: Engine | None = None,
        default_voice: str = DEFAULT_VOICE,
    ) -> None:
        self._cache = cache
        self._engine = engine or _edge_engine
        self._default_voice = default_voice

    def cache_key(self, text: str, voice: VoiceSpec | None = None) -> str:
        spec = voice or VoiceSpec(voice=self._default_voice)
        return self._cache.key(text, spec.voice, spec.rate)

    async def synthesize(self, text: str, voice: VoiceSpec | None = None) -> AudioRef:
        spec = voice or VoiceSpec(voice=self._default_voice)
        digest = self._cache.key(text, spec.voice, spec.rate)

        cached = self._cache.read(digest)
        if cached is None:
            audio = await self._engine(text, spec.voice, spec.rate)
            if not audio:
                raise AiUnavailable("tts engine returned no audio", stage=_stage())
            self._cache.write(digest, audio)
            logger.info("tts_synthesized", voice=spec.voice, bytes=len(audio), digest=digest[:12])
        return AudioRef(
            url=f"/api/v1/media/tts/{digest}.mp3",
            path=str(self._cache.path_for(digest)),
            mime_type="audio/mpeg",
        )

    def cached(self, text: str, voice: VoiceSpec | None = None) -> bytes | None:
        spec = voice or VoiceSpec(voice=self._default_voice)
        return self._cache.read(self._cache.key(text, spec.voice, spec.rate))


def _stage():  # pragma: no cover - tiny helper kept next to its only use
    from ...ai_resilience import Stage

    return Stage.TTS
