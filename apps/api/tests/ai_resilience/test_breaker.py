"""M3-T4: circuit breaker driven by a manual clock (no real waiting)."""

from __future__ import annotations

import time

import pytest

from better_resume.ai_resilience import (
    AiUnavailable,
    BreakerPolicy,
    BreakerState,
    CircuitBreaker,
    ManualClock,
    Stage,
)
from better_resume.ai_resilience.breaker import BreakerRegistry


@pytest.fixture
def policy() -> BreakerPolicy:
    return BreakerPolicy(
        window=5, min_calls=3, failure_rate=0.5, open_seconds=30.0, half_open_permits=2
    )


@pytest.fixture
def clock() -> ManualClock:
    return ManualClock(start=1_000.0)


@pytest.fixture
def breaker(clock: ManualClock, policy: BreakerPolicy) -> CircuitBreaker:
    return CircuitBreaker(stage=Stage.EVALUATION, policy=policy, clock=clock)


def test_failure_rate_opens_the_circuit_and_short_circuits(breaker: CircuitBreaker) -> None:
    assert breaker.state is BreakerState.CLOSED
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.state is BreakerState.CLOSED  # below min_calls

    breaker.record_failure()
    assert breaker.state is BreakerState.OPEN
    assert breaker.allow() is False


def test_min_calls_protects_cold_start(clock: ManualClock) -> None:
    breaker = CircuitBreaker(
        stage=Stage.CHAT,
        policy=BreakerPolicy(window=50, min_calls=10, failure_rate=0.5),
        clock=clock,
    )
    for _ in range(9):
        breaker.record_failure()
    assert breaker.state is BreakerState.CLOSED
    assert breaker.allow() is True


def test_successes_keep_the_circuit_closed(breaker: CircuitBreaker) -> None:
    # Boundary note: the breaker trips at failure_rate >= threshold, so 2 failures out of
    # 4 samples (0.5) would already open it; use 1 failure out of 4 to stay closed.
    breaker.record_failure()
    for _ in range(3):
        breaker.record_success()
    assert breaker.state is BreakerState.CLOSED
    assert breaker.failure_rate == pytest.approx(0.25)


def test_open_wait_then_half_open(breaker: CircuitBreaker, clock: ManualClock) -> None:
    for _ in range(3):
        breaker.record_failure()

    clock.advance(29.9)
    assert breaker.allow() is False

    clock.advance(0.2)
    assert breaker.state is BreakerState.HALF_OPEN
    assert breaker.allow() is True


def test_half_open_success_closes_and_clears_the_window(
    breaker: CircuitBreaker, clock: ManualClock
) -> None:
    for _ in range(3):
        breaker.record_failure()
    clock.advance(31)

    assert breaker.allow() is True
    breaker.record_success()
    assert breaker.state is BreakerState.CLOSED
    assert breaker.snapshot()["samples"] == 0


def test_half_open_failure_reopens_and_restarts_the_wait(
    breaker: CircuitBreaker, clock: ManualClock
) -> None:
    for _ in range(3):
        breaker.record_failure()
    clock.advance(31)
    assert breaker.allow() is True

    breaker.record_failure()
    assert breaker.state is BreakerState.OPEN

    clock.advance(29)
    assert breaker.allow() is False
    clock.advance(2)
    assert breaker.allow() is True


def test_half_open_permits_are_capped(breaker: CircuitBreaker, clock: ManualClock) -> None:
    for _ in range(3):
        breaker.record_failure()
    clock.advance(31)

    assert breaker.allow() is True
    assert breaker.allow() is True
    assert breaker.allow() is False  # third probe is over the permit budget


def test_ensure_allowed_raises_the_taxonomy_error(breaker: CircuitBreaker) -> None:
    for _ in range(3):
        breaker.record_failure()

    with pytest.raises(AiUnavailable) as caught:
        breaker.ensure_allowed()
    assert caught.value.stage is Stage.EVALUATION
    assert caught.value.retryable is True
    assert "circuit open" in str(caught.value)


def test_stages_are_isolated(clock: ManualClock, policy: BreakerPolicy) -> None:
    registry = BreakerRegistry(policy, clock=clock)
    extraction = registry.for_stage(Stage.EXTRACTION)
    evaluation = registry.for_stage(Stage.EVALUATION)

    for _ in range(3):
        extraction.record_failure()

    assert extraction.state is BreakerState.OPEN
    assert evaluation.state is BreakerState.CLOSED
    assert registry.for_stage(Stage.EXTRACTION) is extraction
    assert set(registry.snapshot()) == {"extraction", "evaluation"}


def test_snapshot_reports_state_and_remaining_wait(
    breaker: CircuitBreaker, clock: ManualClock
) -> None:
    for _ in range(3):
        breaker.record_failure()
    clock.advance(10)

    snapshot = breaker.snapshot()
    assert snapshot["state"] == "open"
    assert snapshot["samples"] == 3
    assert snapshot["failure_rate"] == 1.0
    assert snapshot["open_remaining"] == pytest.approx(20.0)


def test_transitions_never_sleep_in_real_time(clock: ManualClock, breaker: CircuitBreaker) -> None:
    started = time.monotonic()
    for _ in range(3):
        breaker.record_failure()
    clock.advance(1_000)
    assert breaker.allow() is True
    assert time.monotonic() - started < 0.5
