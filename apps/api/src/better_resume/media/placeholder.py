"""Explicit M0 placeholders; Xunfei AST / edge-tts adapters land with M4."""

from __future__ import annotations

from .models import AudioRef, ChannelCtx, VoiceSpec

_TRANSCRIPTION_REASON = "TranscriptionChannel (Xunfei AST adapter) is implemented in M4."
_TTS_REASON = "TtsSynthesizer (edge-tts adapter) is implemented in M4."


class UnimplementedTranscriptionChannel:
    async def start(self, ctx: ChannelCtx) -> None:
        raise NotImplementedError(_TRANSCRIPTION_REASON)

    async def feed(self, pcm: bytes) -> None:
        raise NotImplementedError(_TRANSCRIPTION_REASON)

    async def stop(self) -> None:
        raise NotImplementedError(_TRANSCRIPTION_REASON)

    async def wait(self) -> None:
        raise NotImplementedError(_TRANSCRIPTION_REASON)


class UnimplementedTtsSynthesizer:
    async def synthesize(self, text: str, voice: VoiceSpec) -> AudioRef:
        raise NotImplementedError(_TTS_REASON)
