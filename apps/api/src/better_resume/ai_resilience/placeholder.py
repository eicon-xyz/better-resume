"""Explicit M0 placeholder; single-flight/circuit-breaker land with M3."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypeVar

from .models import Stage

T = TypeVar("T")

_REASON = "AiResilience (single-flight + breaker + limiter) is implemented in M3."


class UnimplementedAiResilience:
    async def run(self, stage: Stage, key: str, fn: Callable[[], Awaitable[T]]) -> T:
        raise NotImplementedError(_REASON)
