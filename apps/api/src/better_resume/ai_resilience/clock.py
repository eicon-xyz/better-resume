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


@runtime_checkable
class WallClock(Protocol):
    """Wall-clock **milliseconds** — the only time base several processes can compare (P7).

    `Clock` is monotonic on purpose (durations inside one process), so two replicas cannot
    compare their readings. Bucket state lives in Redis and is written by whichever replica
    arrives first, so the value written into that state must come from a clock every replica
    reads the same way. Assumption: replicas share a roughly synced wall clock (containers on
    one host share the host clock; NTP elsewhere). At 2 tokens/s a 100ms skew is 0.2 tokens.
    """

    def now_ms(self) -> int: ...


class SystemWallClock:
    def now_ms(self) -> int:
        return int(time.time() * 1000)


class ManualWallClock:
    """Deterministic wall clock for tests: no sleeping, just advance_ms()."""

    def __init__(self, start_ms: int = 0) -> None:
        self._now_ms = start_ms

    def now_ms(self) -> int:
        return self._now_ms

    def advance_ms(self, milliseconds: int) -> None:
        if milliseconds < 0:
            raise ValueError("time does not run backwards")
        self._now_ms += milliseconds

    def advance(self, seconds: float) -> None:
        self.advance_ms(int(seconds * 1000))


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
