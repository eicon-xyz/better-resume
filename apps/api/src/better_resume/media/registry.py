"""One transcription channel per user (D15): a second socket is rejected, not merged."""

from __future__ import annotations


class ChannelRegistry:
    def __init__(self) -> None:
        self._active: set[str] = set()

    def try_acquire(self, key: str) -> bool:
        if key in self._active:
            return False
        self._active.add(key)
        return True

    def release(self, key: str) -> None:
        self._active.discard(key)

    @property
    def active(self) -> set[str]:
        return set(self._active)
