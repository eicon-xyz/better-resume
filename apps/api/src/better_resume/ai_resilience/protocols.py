"""AiResilience seam: single-flight + circuit breaker + timeout behind one method (§12.2)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol, TypeVar, runtime_checkable

from .models import Stage

T = TypeVar("T")


@runtime_checkable
class AiResilience(Protocol):
    async def run(self, stage: Stage, key: str, fn: Callable[[], Awaitable[T]]) -> T:
        """Run `fn` under the stage's resilience policy.

        key = stage|sessionId|questionNumber|sha256(payload)
        """
        ...
