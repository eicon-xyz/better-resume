"""Per-stage circuit breaker (§4.1.4): sliding sample window, open wait, half-open probes.

Time comes from the injected Clock so tests never sleep; judgement is lazy (no timers, no
background tasks), which keeps shutdown clean and makes every transition reproducible.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from .clock import Clock, SystemClock
from .errors import AiUnavailable
from .metrics import ResilienceMetrics
from .models import Stage

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..settings import ResilienceSettings


class BreakerState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass(frozen=True, slots=True)
class BreakerPolicy:
    """Old project defaults: window 50, failure rate 50%, open 30s, 10 half-open probes."""

    window: int = 50
    min_calls: int = 10
    failure_rate: float = 0.5
    open_seconds: float = 30.0
    half_open_permits: int = 10

    @classmethod
    def from_settings(cls, settings: ResilienceSettings) -> BreakerPolicy:
        return cls(
            window=settings.breaker_window,
            min_calls=settings.breaker_min_calls,
            failure_rate=settings.breaker_failure_rate,
            open_seconds=settings.breaker_open_seconds,
            half_open_permits=settings.breaker_half_open_permits,
        )


class CircuitBreaker:
    def __init__(
        self,
        *,
        stage: Stage,
        policy: BreakerPolicy,
        clock: Clock | None = None,
        metrics: ResilienceMetrics | None = None,
    ) -> None:
        self.stage = stage
        self.policy = policy
        self._clock = clock or SystemClock()
        self._metrics = metrics or ResilienceMetrics()
        self._state = BreakerState.CLOSED
        self._results: deque[bool] = deque(maxlen=max(1, policy.window))
        self._opened_at = 0.0
        self._half_open_in_flight = 0

    @property
    def state(self) -> BreakerState:
        self._maybe_half_open()
        return self._state

    @property
    def failure_rate(self) -> float:
        if not self._results:
            return 0.0
        return sum(1 for failed in self._results if failed) / len(self._results)

    def allow(self) -> bool:
        state = self.state
        if state is BreakerState.CLOSED:
            return True
        if state is BreakerState.OPEN:
            return False
        if self._half_open_in_flight >= self.policy.half_open_permits:
            return False
        self._half_open_in_flight += 1
        return True

    def ensure_allowed(self) -> None:
        """Raise the taxonomy error the guard chain expects when the circuit is open."""
        if not self.allow():
            self._metrics.breaker_rejected += 1
            raise AiUnavailable(
                f"circuit open ({self._state.value}), retry in {self._open_remaining():.1f}s",
                stage=self.stage,
            )

    def record_success(self) -> None:
        if self._state is BreakerState.OPEN:
            return
        if self._state is BreakerState.HALF_OPEN:
            self._close()
            return
        self._results.append(False)

    def record_failure(self) -> None:
        if self._state is BreakerState.OPEN:
            return
        if self._state is BreakerState.HALF_OPEN:
            self._open()
            return
        self._results.append(True)
        if (
            len(self._results) >= self.policy.min_calls
            and self.failure_rate >= self.policy.failure_rate
        ):
            self._open()

    def snapshot(self) -> dict[str, object]:
        return {
            "stage": self.stage.value,
            "state": self.state.value,
            "samples": len(self._results),
            "failure_rate": round(self.failure_rate, 3),
            "open_remaining": round(self._open_remaining(), 3),
            "half_open_in_flight": self._half_open_in_flight,
        }

    # ---- transitions ------------------------------------------------------------

    def _maybe_half_open(self) -> None:
        if self._state is BreakerState.OPEN and self._open_remaining() <= 0.0:
            self._state = BreakerState.HALF_OPEN
            self._results.clear()
            self._half_open_in_flight = 0

    def _open(self) -> None:
        self._state = BreakerState.OPEN
        self._opened_at = self._clock.now()
        self._half_open_in_flight = 0
        self._metrics.breaker_opened += 1

    def _close(self) -> None:
        self._state = BreakerState.CLOSED
        self._results.clear()
        self._half_open_in_flight = 0

    def _open_remaining(self) -> float:
        if self._state is not BreakerState.OPEN:
            return 0.0
        return max(0.0, self.policy.open_seconds - (self._clock.now() - self._opened_at))


class BreakerRegistry:
    """One breaker per stage: an interview outage must not stop the chat."""

    def __init__(
        self,
        policy: BreakerPolicy,
        *,
        clock: Clock | None = None,
        metrics: ResilienceMetrics | None = None,
    ) -> None:
        self._policy = policy
        self._clock = clock or SystemClock()
        self._metrics = metrics or ResilienceMetrics()
        self._breakers: dict[Stage, CircuitBreaker] = {}

    def for_stage(self, stage: Stage) -> CircuitBreaker:
        breaker = self._breakers.get(stage)
        if breaker is None:
            breaker = CircuitBreaker(
                stage=stage, policy=self._policy, clock=self._clock, metrics=self._metrics
            )
            self._breakers[stage] = breaker
        return breaker

    def snapshot(self) -> dict[str, dict[str, object]]:
        return {stage.value: breaker.snapshot() for stage, breaker in self._breakers.items()}
