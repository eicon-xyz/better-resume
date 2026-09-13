"""media seams: transcription is a channel, synthesis is a task (§12.2)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .models import AudioRef, ChannelCtx, VoiceSpec


@runtime_checkable
class TranscriptionChannel(Protocol):
    async def start(self, ctx: ChannelCtx) -> None: ...

    async def feed(self, pcm: bytes) -> None: ...

    async def stop(self) -> None: ...

    async def wait(self) -> None:
        """Block until the channel ends; raise its failure if it failed.

        Added in M4: the M0 sketch (start/feed/stop) could not tell the WS
        endpoint whether the vendor dropped us.
        """
        ...


@runtime_checkable
class TtsSynthesizer(Protocol):
    async def synthesize(self, text: str, voice: VoiceSpec) -> AudioRef: ...
