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


@runtime_checkable
class AiResilienceSnapshot(Protocol):
    """What GET /resilience/stats and the lifespan need from whatever the chain is wrapped in.

    P8 / settings_observability-03: the chain can be wrapped (Redis single flight) and the wrapper
    answered for nothing — the endpoint raised AttributeError the moment the wrapper was switched
    on, because main.py annotated the wired chain as object and nothing pointed at the gap.
    """

    def stats(self) -> dict[str, Any]:
        """The snapshot the endpoint serves; a wrapper answers for what it wraps."""
        ...

    async def aclose(self) -> None:
        """Release what the chain holds open; the app lifespan calls this."""
        ...
