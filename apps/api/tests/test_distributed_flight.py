"""M6-T2: cross-instance single flight — two RedisFlight instances, one upstream call."""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest
from redis import exceptions as redis_exceptions

from better_resume.ai_resilience import (
    AiInvalid,
    AiOverloaded,
    RedisFlight,
)
from better_resume.ai_resilience.models import Stage
from better_resume.interview_engine.evaluation import ScoreResult as Score  # a real project model
from better_resume.settings import Settings


@pytest.fixture
def redis_url() -> str:
    return Settings(_env_file=None).redis_url


@pytest.fixture
async def instances(redis_url: str):
    """Two independent instances sharing one Redis — i.e. two api processes."""
    first = RedisFlight(redis_url, lease_seconds=0.5, wait_seconds=2.0, poll_seconds=0.01)
    second = RedisFlight(redis_url, lease_seconds=0.5, wait_seconds=2.0, poll_seconds=0.01)
    try:
        await first._client.ping()  # noqa: SLF001 - skip when Redis is absent
    except redis_exceptions.RedisError:
        pytest.skip("redis not reachable")
    yield first, second
    await first._client.flushdb()  # noqa: SLF001
    await first.aclose()
    await second.aclose()


def key() -> str:
    return f"eval|{uuid.uuid4().hex}|1|digest"


async def test_two_instances_call_the_vendor_once(instances) -> None:
    first, second = instances
    calls = 0
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow() -> Score:
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return Score(score=88, feedback="ok")

    shared = key()
    leader = asyncio.create_task(
        first.execute(Stage.EVALUATION, shared, slow, replay_ttl=60, negative_ttl=10)
    )
    await started.wait()
    follower = asyncio.create_task(
        second.execute(Stage.EVALUATION, shared, slow, replay_ttl=60, negative_ttl=10)
    )
    await asyncio.sleep(0.05)
    release.set()

    results = await asyncio.gather(leader, follower)

    assert calls == 1
    assert results[0] == results[1] == Score(score=88, feedback="ok")


async def test_result_is_replayed_across_instances(instances) -> None:
    first, second = instances
    shared = key()
    calls = 0

    async def once() -> Score:
        nonlocal calls
        calls += 1
        return Score(score=70, feedback="first")

    await first.execute(Stage.EVALUATION, shared, once, replay_ttl=60, negative_ttl=0)

    replayed = await second.execute(Stage.EVALUATION, shared, once, replay_ttl=60, negative_ttl=0)

    assert calls == 1
    assert isinstance(replayed, Score) and replayed.feedback == "first"
    assert second.follower_replays == 1


async def test_zero_ttl_never_replays(instances) -> None:
    first, second = instances
    shared = key()
    calls = 0

    async def once() -> Score:
        nonlocal calls
        calls += 1
        return Score(score=float(calls), feedback="x")

    await first.execute(Stage.EVALUATION, shared, once, replay_ttl=0, negative_ttl=0)
    await second.execute(Stage.EVALUATION, shared, once, replay_ttl=0, negative_ttl=0)

    assert calls == 2


async def test_cacheable_failure_is_replayed(instances) -> None:
    first, second = instances
    shared = key()
    calls = 0

    async def failing() -> Score:
        nonlocal calls
        calls += 1
        raise AiInvalid("schema mismatch", stage=Stage.EVALUATION)

    for instance in (first, second):
        with pytest.raises(AiInvalid):
            await instance.execute(
                Stage.EVALUATION, shared, failing, replay_ttl=60, negative_ttl=30
            )

    assert calls == 1


async def test_retryable_failure_is_not_cached(instances) -> None:
    first, second = instances
    shared = key()
    calls = 0

    async def failing() -> Score:
        nonlocal calls
        calls += 1
        raise TimeoutError("vendor slow")

    for instance in (first, second):
        with pytest.raises(Exception):  # noqa: B017 - taxonomy wrapper
            await instance.execute(
                Stage.EVALUATION, shared, failing, replay_ttl=60, negative_ttl=30
            )

    assert calls == 2


async def test_waiter_takes_over_after_the_owner_dies(instances) -> None:
    first, second = instances
    shared = key()
    calls = 0

    # A dead owner: the flight is claimed but nobody renews or publishes it.
    await first._client.set(first.owner_key(shared), "dead-owner", px=300)  # noqa: SLF001
    started = asyncio.get_running_loop().time()

    async def work() -> Score:
        nonlocal calls
        calls += 1
        return Score(score=91, feedback="taken over")

    result = await second.execute(Stage.EVALUATION, shared, work, replay_ttl=60, negative_ttl=0)

    assert calls == 1
    assert result.score == 91
    assert second.takeovers == 1  # it first lost a claim, then claimed the freed flight
    assert asyncio.get_running_loop().time() - started >= 0.3


async def test_stale_owner_cannot_overwrite_a_taken_over_result(instances) -> None:
    first, second = instances
    shared = key()

    await first._client.set(first.owner_key(shared), "new-owner", px=5000)  # noqa: SLF001
    await first._publish(  # noqa: SLF001 - the DRM path: an old owner trying to write
        shared, "stale-owner", {"kind": "scalar", "payload": "stale"}, None, 60
    )

    raw = await first._client.get(first.result_key(shared))  # noqa: SLF001
    assert raw is None  # the write was rejected by the token compare


async def test_waiting_is_bounded_and_reports_overload(instances) -> None:
    first, _second = instances
    shared = key()
    # Real time on purpose: ManualClock would never advance inside a polling loop.
    bounded = RedisFlight(
        Settings(_env_file=None).redis_url,
        lease_seconds=30.0,
        wait_seconds=0.1,
        poll_seconds=0.01,
    )
    try:
        await first._client.set(first.owner_key(shared), "busy-owner", px=30000)  # noqa: SLF001

        with pytest.raises(AiOverloaded, match="without a result"):
            await bounded.execute(
                Stage.EVALUATION, shared, lambda: _never(), replay_ttl=0, negative_ttl=0
            )
    finally:
        await bounded.aclose()


async def _never() -> Score:  # pragma: no cover - never executed
    raise AssertionError("the owner should not run")


async def test_scalar_results_round_trip(instances) -> None:
    first, second = instances
    shared = key()

    await first.execute(Stage.CHAT, shared, lambda: _text(), replay_ttl=60, negative_ttl=0)
    replayed = await second.execute(
        Stage.CHAT, shared, lambda: _text(), replay_ttl=60, negative_ttl=0
    )

    assert replayed == "hello"


async def _text() -> str:
    return "hello"


async def test_foreign_modules_are_refused(instances) -> None:
    first, second = instances
    shared = key()
    await first._client.set(  # noqa: SLF001
        first.result_key(shared),
        json.dumps(
            {
                "token": "t",
                "value": {
                    "kind": "model",
                    "module": "os",
                    "class": "system",
                    "payload": {},
                },
                "error": None,
            }
        ),
        ex=60,
    )

    with pytest.raises(Exception, match="refusing to import"):
        await second.execute(
            Stage.EVALUATION, shared, lambda: _never(), replay_ttl=60, negative_ttl=0
        )
