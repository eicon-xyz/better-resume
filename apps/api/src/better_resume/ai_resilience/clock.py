"""Time seam: production reads the monotonic clock, tests and demos drive a manual one."""

from __future__ import annotations

import asyncio
import time
from typing import Protocol, runtime_checkable


@runtime_checkable
class Clock(Protocol):
    def now(self) -> float: ...

    async def sleep(self, seconds: float) -> None: ...


class SystemClock:
    def now(self) -> float:
        return time.monotonic()

    async def sleep(self, seconds: float) -> None:
        if seconds > 0:
            await asyncio.sleep(seconds)


class ManualClock:
    """Deterministic clock: advance() releases every sleeper whose deadline has passed."""

    def __init__(self, start: float = 0.0) -> None:
        self._now = start
        self._waiters: list[tuple[float, asyncio.Future[None]]] = []

    def now(self) -> float:
        return self._now

    async def sleep(self, seconds: float) -> None:
        if seconds <= 0:
            return
        loop = asyncio.get_running_loop()
        future: asyncio.Future[None] = loop.create_future()
        self._waiters.append((self._now + seconds, future))
        try:
            await future
        finally:
            self._waiters = [
                (deadline, waiter) for deadline, waiter in self._waiters if waiter is not future
            ]

    def advance(self, seconds: float) -> None:
        if seconds < 0:
            raise ValueError("time does not run backwards")
        self._now += seconds
        for deadline, future in list(self._waiters):
            if deadline <= self._now and not future.done():
                future.set_result(None)
