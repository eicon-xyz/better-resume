"""Per-stage bulkhead: bounded concurrency with a bounded wait for a slot (§4.1.4)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from .clock import Clock, SystemClock
from .errors import AiOverloaded
from .metrics import ResilienceMetrics
from .models import Stage
from .timeout import run_with_deadline


class Bulkhead:
    def __init__(
        self,
        *,
        stage: Stage,
        max_concurrency: int,
        queue_wait: float,
        clock: Clock | None = None,
        metrics: ResilienceMetrics | None = None,
    ) -> None:
        self.stage = stage
        self.max_concurrency = max(1, max_concurrency)
        self.queue_wait = queue_wait
        self._clock = clock or SystemClock()
        self._metrics = metrics or ResilienceMetrics()
        self._slots = asyncio.Semaphore(self.max_concurrency)

    @property
    def in_flight(self) -> int:
        return self.max_concurrency - self._slots._value  # noqa: SLF001 - read-only gauge

    @asynccontextmanager
    async def slot(self) -> AsyncIterator[None]:
        await self._acquire()
        self._metrics.in_flight += 1
        self._metrics.peak_in_flight = max(self._metrics.peak_in_flight, self._metrics.in_flight)
        try:
            yield
        finally:
            self._metrics.in_flight -= 1
            self._slots.release()

    async def _acquire(self) -> None:
        if not self._slots.locked():
            await self._slots.acquire()
            return
        self._metrics.queued += 1
        try:
            await run_with_deadline(
                self._slots.acquire(), seconds=self.queue_wait, clock=self._clock
            )
        except TimeoutError as exc:
            self._metrics.overflow_rejected += 1
            raise AiOverloaded(
                f"stage {self.stage.value} is at capacity ({self.max_concurrency} in flight, "
                f"waited {self.queue_wait:g}s)",
                stage=self.stage,
            ) from exc
        finally:
            self._metrics.queued -= 1


class BulkheadRegistry:
    """One bulkhead per stage (chat must not be starved by interview evaluations)."""

    def __init__(
        self,
        policies: object,
        *,
        clock: Clock | None = None,
        metrics: ResilienceMetrics | None = None,
    ) -> None:
        self._policies = policies
        self._clock = clock or SystemClock()
        self._metrics = metrics or ResilienceMetrics()
        self._bulkheads: dict[Stage, Bulkhead] = {}

    def for_stage(self, stage: Stage) -> Bulkhead:
        bulkhead = self._bulkheads.get(stage)
        if bulkhead is None:
            policy = self._policies.for_stage(stage)  # type: ignore[attr-defined]
            bulkhead = Bulkhead(
                stage=stage,
                max_concurrency=policy.max_concurrency,
                queue_wait=policy.queue_wait,
                clock=self._clock,
                metrics=self._metrics,
            )
            self._bulkheads[stage] = bulkhead
        return bulkhead

    def snapshot(self) -> dict[str, dict[str, int]]:
        return {
            stage.value: {"in_flight": bulkhead.in_flight, "limit": bulkhead.max_concurrency}
            for stage, bulkhead in self._bulkheads.items()
        }
