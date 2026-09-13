"""M6-T3: hot state — cache hits, honest invalidation, cross-instance reads, degradation."""

from __future__ import annotations

import asyncio
import uuid

import pytest
from redis import exceptions as redis_exceptions

from better_resume.interview_engine import (
    InMemoryHotState,
    RedisHotState,
    RestoreService,
    RestoreView,
)
from better_resume.interview_engine.models import InterviewSession
from better_resume.interview_engine.session_fsm import SessionStatus
from better_resume.settings import Settings


def view(session_id: str, *, answered: int = 0, source: str = "derived") -> RestoreView:
    session = InterviewSession(
        id=session_id,
        user_id="u-1",
        status=SessionStatus.READY,
        interview_type=None,
        question_count=2,
        resume_score=70.0,
        created_at=__import__("datetime").datetime.now(tz=__import__("datetime").UTC),
        updated_at=__import__("datetime").datetime.now(tz=__import__("datetime").UTC),
    )
    return RestoreView(
        session=session,
        flow_status=__import__(
            "better_resume.interview_engine.flow_fsm", fromlist=["FlowStatus"]
        ).FlowStatus.ASKING,
        current_question_no="1",
        answered=answered,
        total_questions=2,
        source=source,
    )


@pytest.fixture
def redis_url() -> str:
    return Settings(_env_file=None).redis_url


@pytest.fixture
async def store(redis_url: str):
    redis_store = RedisHotState(redis_url, ttl_seconds=60)
    try:
        await redis_store._client.ping()  # noqa: SLF001 - skip when Redis is absent
    except redis_exceptions.RedisError:
        pytest.skip("redis not reachable")
    yield redis_store
    await redis_store._client.flushdb()  # noqa: SLF001
    await redis_store.aclose()


async def test_memory_backend_round_trips() -> None:
    memory = InMemoryHotState()
    session_id = uuid.uuid4().hex

    await memory.put(view(session_id, answered=1), user_id="u-1", ttl_seconds=60)
    cached = await memory.get(user_id="u-1", session_id=session_id)

    assert cached is not None
    assert cached.answered == 1
    assert cached.session.id == session_id


async def test_memory_backend_expires() -> None:
    memory = InMemoryHotState()
    session_id = uuid.uuid4().hex
    await memory.put(view(session_id), user_id="u-1", ttl_seconds=0)
    await asyncio.sleep(0.01)

    assert await memory.get(user_id="u-1", session_id=session_id) is None


async def test_invalidation_removes_the_entry() -> None:
    memory = InMemoryHotState()
    session_id = uuid.uuid4().hex
    await memory.put(view(session_id), user_id="u-1", ttl_seconds=60)

    await memory.invalidate(user_id="u-1", session_id=session_id)

    assert await memory.get(user_id="u-1", session_id=session_id) is None


async def test_cache_is_user_scoped() -> None:
    memory = InMemoryHotState()
    session_id = uuid.uuid4().hex
    await memory.put(view(session_id), user_id="u-1", ttl_seconds=60)

    assert await memory.get(user_id="u-2", session_id=session_id) is None


async def test_redis_round_trip_marks_the_source(store: RedisHotState) -> None:
    session_id = uuid.uuid4().hex
    await store.put(view(session_id, answered=2), user_id="u-1", ttl_seconds=60)

    cached = await store.get(user_id="u-1", session_id=session_id)

    assert cached is not None
    assert cached.answered == 2
    assert cached.source == "hot"


async def test_two_instances_share_the_cache(redis_url: str) -> None:
    first = RedisHotState(redis_url, ttl_seconds=60)
    second = RedisHotState(redis_url, ttl_seconds=60)
    try:
        await first._client.ping()  # noqa: SLF001
    except redis_exceptions.RedisError:
        pytest.skip("redis not reachable")
    session_id = uuid.uuid4().hex
    try:
        await first.put(view(session_id, answered=3), user_id="u-1", ttl_seconds=60)

        assert (await second.get(user_id="u-1", session_id=session_id)).answered == 3
    finally:
        await first._client.flushdb()  # noqa: SLF001
        await first.aclose()
        await second.aclose()


async def test_redis_degrades_when_unreachable() -> None:
    broken = RedisHotState("redis://127.0.0.1:6399/0")

    assert await broken.get(user_id="u", session_id="s") is None  # no exception escapes
    await broken.put(view("s"), user_id="u", ttl_seconds=5)
    await broken.invalidate(user_id="u", session_id="s")
    await broken.aclose()


async def test_restore_uses_the_hot_layer_and_falls_back(
    migrated_database: str,
) -> None:
    """End to end against the real database: hit, invalidate, then derive again."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from better_resume.interview_engine import InterviewSessionRepository

    engine = create_async_engine(migrated_database, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    memory = InMemoryHotState()
    user_id = f"hot-{uuid.uuid4().hex[:8]}"
    try:
        async with factory() as session:
            created = await InterviewSessionRepository(session).create(user_id=user_id)
            await session.commit()

        service = RestoreService(factory, hot_state=memory)
        first = await service.restore(session_id=created.id, user_id=user_id)
        second = await service.restore(session_id=created.id, user_id=user_id)
        await memory.invalidate(user_id=user_id, session_id=created.id)
        third = await service.restore(session_id=created.id, user_id=user_id)

        assert first.source == "derived"
        assert second.source == "hot"
        assert third.source == "derived"
        assert (first.session.id, first.answered) == (second.session.id, second.answered)
    finally:
        await engine.dispose()
