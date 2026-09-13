"""In-process single flight (§4.1.5, shrunk from 8 model classes + 6 Lua scripts to one class).

Semantics kept: concurrent callers of the same key join one execution, completed results
may be replayed for a short per-stage TTL, deterministic failures may be negatively cached,
everything else fails through to every waiter. Streams get the §4.2 treatment: one producer
task, many consumers, no replay once finished. Distributed coordination stays in M6 (D07).
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, TypeVar, cast

import structlog

from .clock import Clock, SystemClock
from .metrics import ResilienceMetrics
from .stream import StreamBroadcast

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
    broadcast: StreamBroadcast[Any] | None = None
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

    def active_stream(self, key: str) -> StreamBroadcast[Any] | None:
        entry = self._entries.get(key)
        return entry.broadcast if entry is not None else None

    async def execute(
        self,
        key: str,
        fn: Callable[[], Awaitable[T]],
        *,
        replay_ttl: float = 0.0,
        negative_ttl: float = 0.0,
        expect_stream: bool = False,
        stream_buffer: int = 1024,
    ) -> T:
        now = self._clock.now()
        existing = self._entries.get(key)
        if existing is not None:
            if existing.state is FlightState.RUNNING:
                existing.followers += 1
                self.metrics.singleflight_follower += 1
                # shield: a cancelled follower must not cancel the shared future
                return self._as_caller(await asyncio.shield(existing.future), key, expect_stream)
            if existing.expires_at > now:
                if existing.state is FlightState.DONE:
                    self.metrics.singleflight_replay += 1
                    return existing.future.result()
                if existing.error is not None and getattr(existing.error, "cacheable", False):
                    self.metrics.singleflight_replay += 1
                    raise existing.error
            self._entries.pop(key, None)

        if not self._make_room(now):
            # Fail open: never turn a full registry into a user-visible failure.
            self.metrics.singleflight_direct += 1
            logger.warning("singleflight_registry_full", key_hash=_key_hash(key))
            direct = await fn()
            if isinstance(direct, AsyncIterator):
                if not expect_stream:
                    raise TypeError(_stream_mismatch(key, stream=True, expected=expect_stream))
                return cast(T, direct)
            if expect_stream:
                raise TypeError(_stream_mismatch(key, stream=False, expected=expect_stream))
            return direct

        loop = asyncio.get_running_loop()
        future: asyncio.Future[Any] = loop.create_future()
        # Nobody may await a failed flight (all followers cancelled): swallow the
        # "exception was never retrieved" warning instead of logging noise later.
        future.add_done_callback(_consume_exception)
        entry = Flight(key=key, state=FlightState.RUNNING, future=future, expires_at=float("inf"))
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

        if isinstance(result, AsyncIterator):
            if not expect_stream:
                raise TypeError(_stream_mismatch(key, stream=True, expected=expect_stream))
            return cast(T, self._open_stream(key, entry, future, result, stream_buffer))
        if expect_stream:
            raise TypeError(_stream_mismatch(key, stream=False, expected=expect_stream))

        entry.state = FlightState.DONE
        entry.expires_at = self._clock.now() + max(0.0, replay_ttl)
        _settle(future, result=result)
        if replay_ttl <= 0:
            # Money question: no replay, so do not keep the value around.
            self._entries.pop(key, None)
        return self._as_caller(result, key, expect_stream)

    def abandon(self, key: str) -> None:
        """Drop a finished flight early (tests and shutdown)."""
        self._entries.pop(key, None)

    def open_streams(self) -> list[StreamBroadcast[Any]]:
        return [entry.broadcast for entry in self._entries.values() if entry.broadcast is not None]

    # ---- internals --------------------------------------------------------------

    def _open_stream(
        self,
        key: str,
        entry: Flight,
        future: asyncio.Future[Any],
        source: AsyncIterator[Any],
        stream_buffer: int,
    ) -> AsyncIterator[Any]:
        broadcast: StreamBroadcast[Any] = StreamBroadcast(
            name=key, max_buffered=stream_buffer, metrics=self.metrics
        )
        entry.broadcast = broadcast
        # The flight lives as long as the stream does: followers keep joining the
        # broadcast, and the entry disappears the moment the producer finishes.
        broadcast.start(source, on_finish=lambda: self._forget_stream(key, entry))
        _settle(future, result=broadcast)
        return broadcast.subscribe()

    def _forget_stream(self, key: str, entry: Flight) -> None:
        entry.state = FlightState.DONE
        entry.expires_at = self._clock.now()
        if self._entries.get(key) is entry:
            self._entries.pop(key, None)

    def _as_caller(self, value: Any, key: str, expect_stream: bool) -> Any:
        """Streams are shared, not copied: each caller gets its own subscription."""
        if isinstance(value, StreamBroadcast):
            if not expect_stream:
                raise TypeError(
                    f"key {_key_hash(key)} is bound to a live stream; this call expects a value"
                )
            return value.subscribe()
        if expect_stream:
            raise TypeError(f"key {_key_hash(key)} produced a value but a stream was expected")
        return value

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


def _stream_mismatch(key: str, *, stream: bool, expected: bool) -> str:
    got = "a stream" if stream else "a value"
    wanted = "a stream" if expected else "a value"
    return f"key {_key_hash(key)} produced {got} but {wanted} was expected"


def _key_hash(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]
