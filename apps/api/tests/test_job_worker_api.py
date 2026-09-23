"""T4: `finish` hands the narrative to the Redis queue and the worker fills it in.

In production the API and the worker are two processes with two event loops, so the test
keeps them apart too: `TestClient` drives the app, `asyncio.run` drives the worker through
its own NullPool engine. Only the queue, the database and the LLM gateway are shared.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable, Iterator

import pytest
import redis.asyncio as aioredis
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from better_resume.ai_resilience import ResilientAiResilience
from better_resume.db import build_session_factory
from better_resume.jobs.queue import JobQueue
from better_resume.llm_gateway import LlmScene
from better_resume.main import create_app
from better_resume.settings import Settings
from better_resume.worker import run_once

from .test_interview_report_api import FakeGateway, login, prepare


def _private_jobs_stream() -> str:
    """A stream no other test can collide with (P40).

    This used to be `f"br:jobs:test:{id(settings):x}"`. CPython reuses object addresses —
    12 freshly built Settings objects yielded only 2 distinct ids — so the "private stream
    per test" was really one or two shared streams. A test that leaves a job behind (the
    freeze test asserts the stream length and stops there) then hands that job to the next
    test's worker, which reports `run_once == 1` while its own report keeps `summary: None`.
    """
    return f"br:jobs:test:{uuid.uuid4().hex[:8]}"


@pytest.fixture
def jobs_settings(settings: Settings, redis_url: str) -> Settings:
    """A private stream per test: the suite shares one Redis instance with other tests."""
    return settings.model_copy(
        update={
            "redis_url": redis_url,
            "jobs_enabled": True,
            "jobs_stream": _private_jobs_stream(),
        }
    )


def test_private_jobs_stream_is_unique_per_call() -> None:
    """P40: pin the property the old address-derived name did not have. Two calls must never
    return the same stream, or two tests end up claiming each other's jobs."""
    assert len({_private_jobs_stream() for _ in range(64)}) == 64


@pytest.fixture
def jobs_client(jobs_settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(jobs_settings)) as test_client:
        yield test_client


@pytest.fixture
def gateway(
    jobs_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> Callable[[FakeGateway], FakeGateway]:
    """Install the fake LLM on the jobs app (the report module owns the fake itself)."""
    monkeypatch.setenv("BR_DEEPSEEK_API_KEY", "sk-test-not-real")

    def install(fake: FakeGateway) -> FakeGateway:
        jobs_client.app.state.llm_gateway_factory = lambda spec, api_key: fake
        return fake

    return install


class _StubResolver:
    """Stands in for `SceneResolver`: the worker only needs `resolve(scene)`."""

    def __init__(self, gateway: FakeGateway) -> None:
        self._gateway = gateway

    async def resolve(self, scene: LlmScene) -> FakeGateway:
        assert scene is LlmScene.REPORT_SUMMARY
        return self._gateway


async def _stream_length(settings: Settings) -> int:
    client = aioredis.from_url(settings.redis_url, decode_responses=True)
    try:
        return int(await client.xlen(settings.jobs_stream))
    finally:
        await client.aclose()


def _run_worker_once(settings: Settings, gateway: FakeGateway) -> int:
    """One pass of the real worker loop on its own event loop, like `python -m ...worker`."""

    async def main() -> int:
        engine = create_async_engine(settings.database_url, poolclass=NullPool)
        session_factory: async_sessionmaker[AsyncSession] = build_session_factory(engine)
        queue = JobQueue(
            settings.redis_url,
            stream=settings.jobs_stream,
            max_attempts=settings.jobs_max_attempts,
        )
        resilience = ResilientAiResilience(settings)
        runtime = {
            "session_factory": session_factory,
            "resilience": resilience,
            "resolver": _StubResolver(gateway),
        }
        try:
            return await run_once(queue, runtime, consumer="test-worker", block_ms=200)
        finally:
            await queue.close()
            await resilience.aclose()
            await engine.dispose()

    return asyncio.run(main())


def test_finish_returns_numbers_immediately_and_queues_the_narrative(
    jobs_client: TestClient,
    jobs_settings: Settings,
    gateway,
    migrated_database: str,
) -> None:
    login(jobs_client)
    gateway(FakeGateway())
    session_id = prepare(jobs_client, answers=3)

    response = jobs_client.post(f"/api/v1/interview/sessions/{session_id}/finish")

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["summary"] is None
    assert payload["summary_pending"] is True
    assert payload["llm_summary_used"] is False
    assert payload["overall_score"] == 82.0
    assert len(payload["turns"]) == 3

    # The narrative really is in the stream, and the report is already readable.
    assert asyncio.run(_stream_length(jobs_settings)) == 1
    stored = jobs_client.get(f"/api/v1/interview/sessions/{session_id}/report")
    assert stored.status_code == 200
    assert stored.json()["summary"] is None
    assert stored.json()["overall_score"] == 82.0


def test_worker_fills_the_summary_of_the_frozen_report(
    jobs_client: TestClient,
    jobs_settings: Settings,
    gateway,
    migrated_database: str,
) -> None:
    login(jobs_client)
    fake = gateway(FakeGateway())
    session_id = prepare(jobs_client, answers=3)
    jobs_client.post(f"/api/v1/interview/sessions/{session_id}/finish")

    assert _run_worker_once(jobs_settings, fake) == 1

    report = jobs_client.get(f"/api/v1/interview/sessions/{session_id}/report").json()
    assert report["summary"] == "整体不错，细节可再展开。"
    assert report["llm_summary_used"] is True
    assert report["overall_score"] == 82.0
    assert len(report["turns"]) == 3

    # Nothing left to do: the job was acked, so a second pass is a no-op.
    assert _run_worker_once(jobs_settings, fake) == 0


def test_repeated_finish_does_not_queue_a_second_job(
    jobs_client: TestClient,
    jobs_settings: Settings,
    gateway,
    migrated_database: str,
) -> None:
    login(jobs_client)
    gateway(FakeGateway())
    session_id = prepare(jobs_client, answers=3)

    first = jobs_client.post(f"/api/v1/interview/sessions/{session_id}/finish")
    second = jobs_client.post(f"/api/v1/interview/sessions/{session_id}/finish")

    assert first.status_code == 201 and second.status_code == 201
    assert second.json()["overall_score"] == first.json()["overall_score"]
    assert second.json()["summary_pending"] is True
    assert asyncio.run(_stream_length(jobs_settings)) == 1
