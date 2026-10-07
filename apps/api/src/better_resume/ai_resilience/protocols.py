"""AiResilience seam: single-flight + circuit breaker + timeout behind one method (§12.2)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol, TypeVar, runtime_checkable

from .models import Stage

T = TypeVar("T")


@runtime_checkable
class AiResilience(Protocol):
    async def run(self, stage: Stage, key: str, fn: Callable[[], Awaitable[T]]) -> T:
        """Run `fn` under the stage's resilience policy.

        key = stage|sessionId|questionNumber|sha256(payload)
        """
        ...

    def stats(self) -> dict[str, Any]:
        """The snapshot GET /resilience/stats serves.

        P8 / settings_observability-03: the chain can be wrapped (Redis single flight) and the
        wrapper had no way to answer for what it wraps — while main.py annotated the wired chain
        as `object`, so nothing pointed at the gap until the wrapper was switched on.
        """
        ...

    async def aclose(self) -> None:
        """Release what the chain holds open; the app lifespan calls this."""
        ...
