"""In-process single flight (§4.1.5, shrunk from 8 model classes + 6 Lua scripts to one class).

Semantics kept: concurrent callers of the same key join one execution, completed results
may be replayed for a short per-stage TTL, deterministic failures may be negatively cached,
everything else fails through to every waiter. Distributed coordination stays in M6 (D07).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, TypeVar

import structlog

from .clock import Clock, SystemClock
from .metrics import ResilienceMetrics

logger = structlog.get_logger("better_resume.ai_resilience.singleflight")

T = TypeVar("T")


class FlightState(StrEnum):
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass
class Flight:
    key: str
    state: FlightState
    future: asyncio.Future[Any]
    expires_at: float
    error: BaseException | None = None
    followers: int = 0
    log_context: dict[str, Any] = field(default_factory=dict)


class SingleFlight:
    """One method: run fn once per key, let everybody else in on the result."""

    def __init__(
        self,
        *,
        clock: Clock | None = None,
        max_entries: int = 256,
        metrics: ResilienceMetrics | None = None,
    ) -> None:
        self._clock = clock or SystemClock()
        self._max_entries = max(1, max_entries)
        self._entries: dict[str, Flight] = {}
        self.metrics = metrics or ResilienceMetrics()

    @property
    def entry_count(self) -> int:
        return len(self._entries)

    async def execute(
        self,
        key: str,
        fn: Callable[[], Awaitable[T]],
        *,
        replay_ttl: float = 0.0,
        negative_ttl: float = 0.0,
    ) -> T:
        now = self._clock.now()
        existing = self._entries.get(key)
        if existing is not None:
            if existing.state is FlightState.RUNNING:
                existing.followers += 1
                self.metrics.singleflight_follower += 1
                # shield: a cancelled follower must not cancel the shared future
                return await asyncio.shield(existing.future)
            if existing.expires_at > now:
                if existing.state is FlightState.DONE:
                    self.metrics.singleflight_replay += 1
                    return existing.future.result()
                if existing.error is not None and getattr(existing.error, "cacheable", False):
                    self.metrics.singleflight_replay += 1
                    raise existing.error
            self._entries.pop(key, None)

        if not self._make_room(now):
            self.metrics.singleflight_direct += 1
            logger.warning("singleflight_registry_full", key_hash=_key_hash(key))
            return await fn()

        loop = asyncio.get_running_loop()
        future: asyncio.Future[Any] = loop.create_future()
        # Nobody may await a failed flight (all followers cancelled): swallow the
        # "exception was never retrieved" warning instead of logging noise later.
        future.add_done_callback(_consume_exception)
        entry = Flight(
            key=key,
            state=FlightState.RUNNING,
            future=future,
            expires_at=float("inf"),
        )
        self._entries[key] = entry
        self.metrics.singleflight_leader += 1

        try:
            result = await fn()
        except BaseException as exc:  # noqa: BLE001 - every failure must reach the waiters
            cacheable = bool(getattr(exc, "cacheable", False))
            entry.state = FlightState.FAILED
            entry.error = exc
            entry.expires_at = self._clock.now() + (negative_ttl if cacheable else 0.0)
            self.metrics.singleflight_error += 1
            _settle(future, exception=exc)  # waiters always learn about the failure
            if not (cacheable and negative_ttl > 0):
                self._entries.pop(key, None)
            raise
        else:
            entry.state = FlightState.DONE
            entry.expires_at = self._clock.now() + max(0.0, replay_ttl)
            _settle(future, result=result)
            if replay_ttl <= 0:
                # Money question: no replay, so do not keep the value around.
                self._entries.pop(key, None)
            return result

    def abandon(self, key: str) -> None:
        """Drop a finished flight early (tests and shutdown)."""
        self._entries.pop(key, None)

    def _make_room(self, now: float) -> bool:
        if len(self._entries) < self._max_entries:
            return True
        for key, entry in list(self._entries.items()):
            if entry.state is not FlightState.RUNNING and entry.expires_at <= now:
                self._entries.pop(key, None)
        return len(self._entries) < self._max_entries


def _settle(
    future: asyncio.Future[Any],
    *,
    result: Any = None,
    exception: BaseException | None = None,
) -> None:
    if future.done():
        return
    if exception is not None:
        future.set_exception(exception)
    else:
        future.set_result(result)


def _consume_exception(future: asyncio.Future[Any]) -> None:
    if not future.cancelled():
        future.exception()


def _key_hash(key: str) -> str:
    import hashlib

    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]
