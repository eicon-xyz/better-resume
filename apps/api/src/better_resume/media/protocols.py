"""media seams: transcription is a channel, synthesis is a task (§12.2)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .models import AudioRef, ChannelCtx, VoiceSpec


@runtime_checkable
class TranscriptionChannel(Protocol):
    async def start(self, ctx: ChannelCtx) -> None: ...

    async def feed(self, pcm: bytes) -> None: ...

    async def stop(self) -> None: ...


@runtime_checkable
class TtsSynthesizer(Protocol):
    async def synthesize(self, text: str, voice: VoiceSpec) -> AudioRef: ...
