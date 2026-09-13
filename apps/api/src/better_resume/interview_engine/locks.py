"""Process-local question locks (M6 swaps this for a Redis lock behind the same seam)."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from dataclasses import dataclass, field


@dataclass
class _Entry:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    waiters: int = 0


class QuestionLockRegistry:
    """One lock per (session, question); entries disappear once nobody holds them."""

    def __init__(self) -> None:
        self._entries: dict[tuple[str, str], _Entry] = {}

    @contextlib.asynccontextmanager
    async def acquire(self, session_id: str, question_no: str) -> AsyncIterator[None]:
        key = (session_id, question_no)
        entry = self._entries.get(key)
        if entry is None:
            entry = _Entry()
            self._entries[key] = entry
        entry.waiters += 1
        try:
            async with entry.lock:
                yield
        finally:
            entry.waiters -= 1
            if entry.waiters <= 0:
                self._entries.pop(key, None)

    def active_keys(self) -> list[tuple[str, str]]:
        return sorted(self._entries)
