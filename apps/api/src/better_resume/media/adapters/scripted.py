"""Scripted transcription channel: same seam, deterministic output (CI + local demo).

This is **not** a mock of an internal module: it implements the TranscriptionChannel
boundary and drives the *real* assembler, so tests exercise the pgs/rg/merge rules too.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from ..assembler import AstTranscriptionAssembler
from ..models import AstPacket, ChannelCtx, TranscriptEvent, TranscriptUpdate

EventSink = Callable[[TranscriptEvent], Awaitable[None] | None]


@dataclass(frozen=True)
class ScriptStep:
    """Apply this packet once at least after_bytes of audio have been fed."""

    after_bytes: int
    text: str
    seg_id: int | None = None
    pgs: str | None = None
    rg: tuple[int, int] | None = None
    final: bool = False


DEFAULT_SCRIPT: tuple[ScriptStep, ...] = (
    ScriptStep(after_bytes=1280, text="我负责", seg_id=1),
    ScriptStep(after_bytes=2560, text="我负责了订单写入链路的重构", seg_id=1),
    ScriptStep(after_bytes=3840, text="我负责了订单写入链路的重构。", seg_id=1, final=True),
)


@dataclass
class ScriptedTranscriptionChannel:
    """Feeds the assembler from a script keyed on audio volume."""

    on_event: EventSink
    steps: tuple[ScriptStep, ...] = DEFAULT_SCRIPT
    _received: int = field(default=0, init=False)
    _cursor: int = field(default=0, init=False)
    _stopped: bool = field(default=False, init=False)
    _committed_seen: str = field(default="", init=False)
    _assembler: AstTranscriptionAssembler = field(
        default_factory=AstTranscriptionAssembler, init=False
    )
    started: bool = field(default=False, init=False)
    stopped_calls: int = field(default=0, init=False)
    _finished: asyncio.Event = field(default_factory=asyncio.Event, init=False)

    async def start(self, ctx: ChannelCtx) -> None:
        self.started = True
        self._stopped = False
        self._finished.clear()

    async def feed(self, pcm: bytes) -> None:
        if self._stopped or not self.started:
            return
        self._received += len(pcm)
        while (
            self._cursor < len(self.steps)
            and self._received >= self.steps[self._cursor].after_bytes
        ):
            step = self.steps[self._cursor]
            self._cursor += 1
            await self._apply(step)

    async def wait(self) -> None:
        """Ready-to-serve channels finish only when stopped."""
        await self._finished.wait()

    async def stop(self) -> None:
        self.stopped_calls += 1
        if self._stopped:
            self._finished.set()
            return
        self._stopped = True
        self._finished.set()
        snapshot = self._assembler.snapshot()
        if snapshot.display:
            await self._emit(TranscriptEvent(kind="final", text=snapshot.display))

    async def _apply(self, step: ScriptStep) -> None:
        from ..models import PgsKind

        packet = AstPacket(
            text=step.text,
            seg_id=step.seg_id,
            pgs=PgsKind(step.pgs) if step.pgs in ("apd", "rpl") else None,
            rg=step.rg,
            final=step.final,
        )
        update = self._assembler.apply(packet)
        if update.final_packet:
            if len(update.committed) > len(self._committed_seen):
                newly = update.committed[len(self._committed_seen) :]
                self._committed_seen = update.committed
                await self._emit(TranscriptEvent(kind="archive", text=newly))
            return
        if update.changed:
            await self._emit(TranscriptEvent(kind="replace", text=update.live))

    async def _emit(self, event: TranscriptEvent) -> None:
        result = self.on_event(event)
        if hasattr(result, "__await__"):
            await result  # type: ignore[misc]

    def snapshot(self) -> TranscriptUpdate:
        return self._assembler.snapshot()
