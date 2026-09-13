"""M6-T4: job queue semantics (real Redis) and the report-summary worker path."""

from __future__ import annotations

import uuid

import pytest
from redis import exceptions as redis_exceptions

from better_resume.jobs import (
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_QUEUED,
    STATUS_RUNNING,
    Job,
    JobQueue,
)
from better_resume.settings import Settings
from better_resume.worker import run_once


@pytest.fixture
def redis_url() -> str:
    return Settings(_env_file=None).redis_url


@pytest.fixture
async def queue(redis_url: str):
    stream = f"br:jobs:test:{uuid.uuid4().hex[:8]}"
    job_queue = JobQueue(redis_url, stream=stream, max_attempts=2)
    try:
        await job_queue._client.ping()  # noqa: SLF001 - skip when Redis is absent
    except redis_exceptions.RedisError:
        pytest.skip("redis not reachable")
    yield job_queue
    await job_queue._client.flushdb()  # noqa: SLF001
    await job_queue.close()


async def test_enqueue_then_ack(queue: JobQueue) -> None:
    task_id, created = await queue.enqueue("demo", {"n": 1}, idempotency_key="once")

    assert created is True
    assert (await queue.status(task_id))["status"] == STATUS_QUEUED

    jobs = await queue.claim(consumer="c1", block_ms=50)
    assert [job.task_id for job in jobs] == [task_id]
    assert jobs[0].payload == {"n": 1}

    await queue.mark_running(jobs[0])
    assert (await queue.status(task_id))["status"] == STATUS_RUNNING

    await queue.ack(jobs[0], result={"ok": True})
    status = await queue.status(task_id)
    assert status["status"] == STATUS_DONE
    assert "ok" in status["result"]


async def test_enqueue_is_idempotent(queue: JobQueue) -> None:
    first, created = await queue.enqueue("demo", {"n": 1}, idempotency_key="same")
    second, again = await queue.enqueue("demo", {"n": 2}, idempotency_key="same")

    assert created is True and again is False
    assert first == second

    stream_len = await queue._client.xlen(queue.stream)  # noqa: SLF001
    assert stream_len == 1


async def test_failure_is_retried_then_dead_lettered(queue: JobQueue) -> None:
    task_id, _ = await queue.enqueue("demo", {"n": 1}, idempotency_key="retry")
    first = (await queue.claim(consumer="c1", block_ms=50))[0]

    assert await queue.fail(first, error="boom") == STATUS_QUEUED
    assert (await queue.status(task_id))["attempts"] == "1"

    second = (await queue.claim(consumer="c1", block_ms=50))[0]
    assert second.attempts == 1
    assert await queue.fail(second, error="boom again") == STATUS_FAILED
    assert (await queue.status(task_id))["status"] == STATUS_FAILED

    dead = await queue._client.xrange(queue.dead_letter_stream)  # noqa: SLF001
    assert len(dead) == 1
    assert dead[0][1]["task_id"] == task_id


async def test_unacked_jobs_are_reclaimed_after_a_crash(queue: JobQueue) -> None:
    task_id, _ = await queue.enqueue("demo", {"n": 1}, idempotency_key="crash")
    claimed = await queue.claim(consumer="dead-worker", block_ms=50)
    assert claimed  # claimed but never acked

    reclaimed = await queue.reclaim_stale(consumer="fresh-worker", min_idle_ms=0)

    assert [job.task_id for job in reclaimed] == [task_id]


async def test_run_once_processes_a_registered_handler(queue: JobQueue, monkeypatch) -> None:
    seen: list[Job] = []

    async def handler(job: Job, runtime: object) -> dict[str, object]:
        seen.append(job)
        return {"echo": job.payload}

    monkeypatch.setitem(
        __import__("better_resume.worker", fromlist=["HANDLERS"]).HANDLERS, "demo", handler
    )
    task_id, _ = await queue.enqueue("demo", {"n": 7}, idempotency_key="run")

    processed = await run_once(queue, {}, consumer="c1", block_ms=50)

    assert processed == 1
    assert seen and seen[0].task_id == task_id
    assert (await queue.status(task_id))["status"] == STATUS_DONE


async def test_run_once_dead_letters_unknown_kinds(queue: JobQueue) -> None:
    task_id, _ = await queue.enqueue("nope", {}, idempotency_key="unknown")

    # max_attempts=2: the first failure schedules a retry, the second dead-letters.
    await run_once(queue, {}, consumer="c1", block_ms=50)
    assert (await queue.status(task_id))["status"] == STATUS_QUEUED
    await run_once(queue, {}, consumer="c1", block_ms=50)

    assert (await queue.status(task_id))["status"] == STATUS_FAILED


async def test_pending_counts_claimed_jobs(queue: JobQueue) -> None:
    await queue.enqueue("demo", {}, idempotency_key="pending")
    await queue.claim(consumer="c1", block_ms=50)

    assert await queue.pending() == 1
