"""M1 stand-in for the resilience seam: call straight through.

Single-flight / breaker / limiter land in M3; the call sites already use `run()` so that
swap happens in one place (§12.2).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypeVar

from .models import Stage

T = TypeVar("T")


class DirectAiResilience:
    async def run(self, stage: Stage, key: str, fn: Callable[[], Awaitable[T]]) -> T:
        return await fn()
