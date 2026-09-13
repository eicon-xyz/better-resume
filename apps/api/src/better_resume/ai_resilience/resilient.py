"""ResilientAiResilience: the whole §4.1.4 guard chain behind one method.

Order (fixed, mirrors AiCallGuardService): single flight -> circuit breaker -> bulkhead ->
deadline -> upstream. The breaker lives *inside* the flight so a rejected call never takes a
slot, and followers of an in-flight call are never rejected mid-wait. Retries are not part
of this chain: llm-gateway already owns them (one retry owner, see README §4).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, TypeVar, cast

import structlog

from ..settings import Settings
from .breaker import BreakerPolicy, BreakerRegistry, CircuitBreaker
from .bulkhead import BulkheadRegistry
from .clock import Clock, SystemClock
from .errors import AiResilienceError, FailureKind, wrap
from .metrics import ResilienceMetrics
from .models import Stage
from .policy import StagePolicies, StagePolicy
from .singleflight import SingleFlight
from .timeout import with_timeout, wrap_stream_timeout

logger = structlog.get_logger("better_resume.ai_resilience")

T = TypeVar("T")


class ResilientAiResilience:
    def __init__(
        self,
        settings: Settings,
        *,
        clock: Clock | None = None,
        metrics: ResilienceMetrics | None = None,
    ) -> None:
        self._settings = settings
        self._clock = clock or SystemClock()
        self.metrics = metrics or ResilienceMetrics()
        self._enabled = settings.resilience.enabled
        self._policies = StagePolicies.from_settings(settings)
        self._flight = SingleFlight(
            clock=self._clock,
            max_entries=settings.resilience.singleflight_max_entries,
            metrics=self.metrics,
        )
        self._breakers = BreakerRegistry(
            BreakerPolicy.from_settings(settings.resilience),
            clock=self._clock,
            metrics=self.metrics,
        )
        self._bulkheads = BulkheadRegistry(self._policies, clock=self._clock, metrics=self.metrics)

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def run(self, stage: Stage, key: str, fn: Callable[[], Awaitable[T]]) -> T:
        if not self._enabled:
            return await fn()

        policy = self._policies.for_stage(stage)
        started = self._clock.now()
        logger.debug("ai_call_started", stage=stage.value, key_hash=_key_hash(key))

        try:
            result = await self._flight.execute(
                key,
                lambda: self._guarded(stage, policy, fn),
                replay_ttl=policy.replay_ttl,
                negative_ttl=policy.negative_ttl,
                expect_stream=policy.is_stream,
                stream_buffer=self._settings.resilience.stream_buffer_frames,
            )
        except AiResilienceError as exc:
            if exc.kind is FailureKind.TIMEOUT:
                self.metrics.timeouts += 1
            logger.warning(
                "ai_call_failed",
                stage=stage.value,
                key_hash=_key_hash(key),
                kind=exc.kind.value,
                duration=round(self._clock.now() - started, 3),
                error=str(exc),
            )
            raise
        else:
            logger.debug(
                "ai_call_finished",
                stage=stage.value,
                key_hash=_key_hash(key),
                duration=round(self._clock.now() - started, 3),
                stream=policy.is_stream,
            )
            return result

    async def aclose(self) -> None:
        """Cancel every in-flight stream producer (clean shutdown, no dangling tasks)."""
        for broadcast in self._flight.open_streams():
            await broadcast.aclose()

    def stats(self) -> dict[str, Any]:
        return {
            "enabled": self._enabled,
            "policies": {
                stage.value: {
                    "timeout": policy.timeout,
                    "max_concurrency": policy.max_concurrency,
                    "queue_wait": policy.queue_wait,
                    "replay_ttl": policy.replay_ttl,
                    "is_stream": policy.is_stream,
                }
                for stage in Stage
                for policy in [self._policies.for_stage(stage)]
            },
            "breakers": self._breakers.snapshot(),
            "bulkheads": self._bulkheads.snapshot(),
            "singleflight": {
                "entries": self._flight.entry_count,
                "open_streams": len(self._flight.open_streams()),
            },
            "metrics": self.metrics.snapshot(),
        }

    # ---- the guard chain --------------------------------------------------------

    async def _guarded(
        self, stage: Stage, policy: StagePolicy, fn: Callable[[], Awaitable[T]]
    ) -> T:
        breaker = self._breakers.for_stage(stage)
        breaker.ensure_allowed()  # rejected calls never occupy a bulkhead slot

        async with self._bulkheads.for_stage(stage).slot():
            opened_at = self._clock.now()
            try:
                opened = await with_timeout(stage, policy.timeout, fn(), clock=self._clock)
            except asyncio.CancelledError:
                raise
            except BaseException as exc:  # noqa: BLE001 - everything is normalised here
                raise self._record_failure(breaker, exc, stage=stage) from exc

            if not policy.is_stream:
                breaker.record_success()
                return opened

            # Streams: the breaker learns the outcome when the stream ends, so one
            # consumer (the broadcast producer) drives the wrapper exactly once.
            spent = self._clock.now() - opened_at
            return cast(
                T,
                self._observe_stream(
                    cast(AsyncIterator[Any], opened),
                    stage=stage,
                    breaker=breaker,
                    budget=max(0.0, policy.timeout - spent),
                ),
            )

    async def _observe_stream(
        self,
        source: AsyncIterator[Any],
        *,
        stage: Stage,
        breaker: CircuitBreaker,
        budget: float,
    ) -> AsyncIterator[Any]:
        try:
            async for frame in wrap_stream_timeout(
                source, stage=stage, timeout=budget, clock=self._clock
            ):
                yield frame
        except (asyncio.CancelledError, GeneratorExit):
            raise
        except BaseException as exc:  # noqa: BLE001 - normalise for the breaker and caller
            raise self._record_failure(breaker, exc, stage=stage) from exc
        else:
            breaker.record_success()

    def _record_failure(
        self, breaker: CircuitBreaker, exc: BaseException, *, stage: Stage
    ) -> AiResilienceError:
        wrapped = wrap(exc, stage=stage)
        # Bulkhead rejections are our own backpressure, not vendor health: they must not
        # push the circuit open (the old project made the same distinction).
        if wrapped.kind is not FailureKind.OVERLOADED:
            breaker.record_failure()
        return wrapped


def _key_hash(key: str) -> str:
    import hashlib

    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]
