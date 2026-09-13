"""M3-T7: one run() hiding the whole guard chain (order, taxonomy, shutdown, stats)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

from better_resume.ai_resilience import (
    AiInvalid,
    AiOverloaded,
    AiTimeout,
    AiUnavailable,
    ManualClock,
    ResilienceMetrics,
    ResilientAiResilience,
    Stage,
)
from better_resume.llm_gateway import LlmSchemaError, LlmTimeoutError
from better_resume.settings import ResilienceSettings, Settings


async def settle(times: int = 6) -> None:
    for _ in range(times):
        await asyncio.sleep(0)


async def collect(stream: AsyncIterator[object]) -> list[object]:
    frames: list[object] = []
    async for frame in stream:
        frames.append(frame)
    return frames


def build(clock: ManualClock, **overrides: object) -> ResilientAiResilience:
    settings = Settings(_env_file=None, resilience=ResilienceSettings(**overrides))  # type: ignore[arg-type]
    return ResilientAiResilience(settings, clock=clock, metrics=ResilienceMetrics())


async def test_value_passes_through_and_is_counted() -> None:
    clock = ManualClock()
    service = build(clock)

    async def fn() -> str:
        return "ok"

    assert await service.run(Stage.EVALUATION, "eval|s|1|digest", fn) == "ok"
    snapshot = service.metrics.snapshot()
    assert snapshot["singleflight_leader"] == 1
    assert snapshot["timeouts"] == 0
    assert service.stats()["breakers"]["evaluation"]["state"] == "closed"


async def test_bulkhead_rejection_does_not_touch_the_breaker() -> None:
    clock = ManualClock()
    service = build(
        clock,
        evaluation_max_concurrency=1,
        queue_wait_seconds=1.0,
        breaker_min_calls=1,
        breaker_window=5,
    )
    release = asyncio.Event()

    async def hold() -> str:
        await release.wait()
        return "ok"

    leader = asyncio.create_task(service.run(Stage.EVALUATION, "k1", hold))
    await settle()
    waiter = asyncio.create_task(service.run(Stage.EVALUATION, "k2", hold))
    await settle()

    clock.advance(1.1)
    with pytest.raises(AiOverloaded):
        await waiter

    breaker = service.stats()["breakers"]["evaluation"]
    assert breaker["samples"] == 0  # backpressure is not vendor health
    assert breaker["state"] == "closed"

    release.set()
    assert await leader == "ok"


async def test_open_circuit_rejects_without_taking_a_slot() -> None:
    clock = ManualClock()
    service = build(clock, evaluation_max_concurrency=1, breaker_min_calls=1, breaker_window=2)

    async def boom() -> str:
        raise LlmTimeoutError("vendor down")

    with pytest.raises(AiTimeout):
        await service.run(Stage.EVALUATION, "k1", boom)

    with pytest.raises(AiUnavailable):
        await service.run(Stage.EVALUATION, "k2", boom)

    assert service.stats()["bulkheads"]["evaluation"]["in_flight"] == 0
    assert service.metrics.snapshot()["breaker_rejected"] == 1


async def test_deadline_failure_is_wrapped_and_counted() -> None:
    clock = ManualClock()
    service = build(clock, evaluation_timeout_seconds=5.0, breaker_min_calls=1)

    async def slow() -> str:
        await asyncio.Event().wait()
        return "never"

    task = asyncio.create_task(service.run(Stage.EVALUATION, "k", slow))
    await settle()
    clock.advance(5.1)

    with pytest.raises(AiTimeout):
        await task

    assert service.metrics.snapshot()["timeouts"] == 1
    assert service.stats()["breakers"]["evaluation"]["state"] == "open"


async def test_schema_failure_is_negative_cached_then_retried() -> None:
    clock = ManualClock()
    service = build(clock, negative_cache_seconds=10.0, breaker_min_calls=100)
    calls = 0

    async def bad() -> str:
        nonlocal calls
        calls += 1
        raise LlmSchemaError("vendor returned prose")

    for _ in range(2):
        with pytest.raises(AiInvalid):
            await service.run(Stage.EVALUATION, "k", bad)
    assert calls == 1

    clock.advance(11)
    with pytest.raises(AiInvalid):
        await service.run(Stage.EVALUATION, "k", bad)
    assert calls == 2


async def test_followers_of_an_inflight_call_are_never_rejected() -> None:
    clock = ManualClock()
    service = build(clock, evaluation_max_concurrency=4, breaker_min_calls=1, breaker_window=4)
    release = asyncio.Event()

    async def hold() -> str:
        await release.wait()
        return "shared"

    leader = asyncio.create_task(service.run(Stage.EVALUATION, "same", hold))
    await settle()
    follower = asyncio.create_task(service.run(Stage.EVALUATION, "same", hold))
    await settle()

    async def boom() -> str:
        raise LlmTimeoutError("vendor down")

    with pytest.raises(AiTimeout):
        await service.run(Stage.EVALUATION, "other", boom)
    assert service.stats()["breakers"]["evaluation"]["state"] == "open"

    release.set()
    assert await leader == "shared"
    assert await follower == "shared"


async def test_streams_flow_through_the_chain() -> None:
    clock = ManualClock()
    service = build(clock, chat_max_concurrency=2)

    async def source() -> AsyncIterator[str]:
        for index in range(3):
            yield f"f{index}"

    async def open_stream() -> AsyncIterator[str]:
        return source()

    streams = await asyncio.gather(
        service.run(Stage.CHAT, "chat|s|h", open_stream),
        service.run(Stage.CHAT, "chat|s|h", open_stream),
    )
    texts = await asyncio.gather(*(collect(stream) for stream in streams))

    assert texts == [["f0", "f1", "f2"]] * 2
    assert service.metrics.snapshot()["singleflight_follower"] == 1
    await settle()
    assert service.stats()["breakers"]["chat"]["state"] == "closed"
    assert service.stats()["breakers"]["chat"]["samples"] == 1


async def test_stream_budget_failure_reaches_the_consumer() -> None:
    clock = ManualClock()
    service = build(clock, chat_timeout_seconds=10.0, breaker_min_calls=1)

    async def source() -> AsyncIterator[str]:
        yield "a"
        await asyncio.Event().wait()

    async def open_stream() -> AsyncIterator[str]:
        return source()

    stream = await service.run(Stage.CHAT, "chat|s|h", open_stream)
    assert await anext(stream) == "a"
    # The producer must reach its next deadline wait before we move the clock (see P5).
    await settle()

    clock.advance(10.1)
    with pytest.raises(AiTimeout):
        await anext(stream)

    assert service.stats()["breakers"]["chat"]["state"] == "open"


async def test_aclose_cancels_open_streams() -> None:
    clock = ManualClock()
    service = build(clock)

    async def source() -> AsyncIterator[int]:
        while True:
            await asyncio.sleep(0)
            yield 1

    async def open_stream() -> AsyncIterator[int]:
        return source()

    stream = await service.run(Stage.CHAT, "chat|s|h", open_stream)
    assert await anext(stream) == 1

    await service.aclose()
    await settle()

    assert service.stats()["singleflight"]["open_streams"] == 0
    assert service.stats()["metrics"]["singleflight_abandoned"] >= 1


async def test_disabled_service_is_a_passthrough() -> None:
    clock = ManualClock()
    service = build(clock, enabled=False)
    calls = 0
    release = asyncio.Event()

    async def fn() -> str:
        nonlocal calls
        calls += 1
        await release.wait()
        return "v"

    tasks = [asyncio.create_task(service.run(Stage.EVALUATION, "k", fn)) for _ in range(2)]
    await settle(4)
    release.set()

    assert await asyncio.gather(*tasks) == ["v", "v"]
    assert calls == 2  # no single flight when the chain is switched off


async def test_stats_describe_every_stage() -> None:
    service = build(ManualClock())
    stats = service.stats()

    assert stats["enabled"] is True
    assert set(stats["policies"]) == {"chat", "extraction", "evaluation", "followup", "tts"}
    assert stats["policies"]["chat"]["is_stream"] is True
    assert stats["policies"]["evaluation"]["is_stream"] is False
    assert set(stats["metrics"]) >= {"singleflight_leader", "breaker_opened", "rate_limited"}
