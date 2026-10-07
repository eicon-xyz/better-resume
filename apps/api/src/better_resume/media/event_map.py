"""One mapping from assembler updates to transcript events (P8 / media-01).

Two adapters carried this block line for line — `xunfei_ast` (the vendor channel) and `scripted`
(the default channel in CI and local runs) — and nothing required them to stay equal: editing one
was enough to make the two disagree about what a committed sentence is. The rule and its memory
(how much of the committed text the client has already seen) live here together, so they cannot
drift apart.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import TranscriptEvent, TranscriptUpdate


@dataclass
class TranscriptEventMapper:
    """Turn assembler snapshots into the frames a client should see."""

    _committed_seen: str = field(default="", init=False)

    def events(self, update: TranscriptUpdate) -> list[TranscriptEvent]:
        # Protocol: non-final packets rewrite the live area; a final packet only appends the newly
        # committed sentence (clients clear their live area on archive).
        if update.final_packet:
            if len(update.committed) > len(self._committed_seen):
                newly = update.committed[len(self._committed_seen) :]
                self._committed_seen = update.committed
                return [TranscriptEvent(kind="archive", text=newly)]
            return []
        if update.changed:
            return [TranscriptEvent(kind="replace", text=update.live)]
        return []
