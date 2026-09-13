"""T2: answer-flow FSM + version CAS against a real database."""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from better_resume.interview_engine.errors import IllegalFlowTransition
from better_resume.interview_engine.flow_fsm import (
    FLOW_TRANSITIONS,
    FlowStatus,
    ensure_flow_transition,
)
from better_resume.interview_engine.flow_store import FlowStateStore

ALLOWED = {
    ("init", "asking"),
    ("init", "completed"),
    ("asking", "evaluating"),
    ("asking", "completed"),
    ("evaluating", "asking"),
    ("evaluating", "follow_up"),
    ("evaluating", "completed"),
    ("follow_up", "evaluating"),
    ("follow_up", "asking"),
    ("follow_up", "completed"),
}


@pytest.mark.parametrize("source", list(FlowStatus))
@pytest.mark.parametrize("target", list(FlowStatus))
def test_flow_transition_table_is_exhaustive(source: FlowStatus, target: FlowStatus) -> None:
    allowed = (source.value, target.value) in ALLOWED or source == target

    if allowed:
        ensure_flow_transition(source, target)
    else:
        with pytest.raises(IllegalFlowTransition):
            ensure_flow_transition(source, target)


def test_completed_is_terminal() -> None:
    assert FLOW_TRANSITIONS[FlowStatus.COMPLETED] == frozenset()


@pytest.fixture
async def factory(migrated_database: str):
    engine = create_async_engine(migrated_database, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    yield session_factory
    await engine.dispose()


@pytest.fixture
async def session_id(factory) -> str:
    from better_resume.interview_engine.session_repo import InterviewSessionRepository

    async with factory() as session:
        created = await InterviewSessionRepository(session).create(user_id="u-flow")
        await session.commit()
        return created.id


async def test_initialize_and_mutate_bumps_version(factory, session_id: str) -> None:
    async with factory() as session:
        store = FlowStateStore(session)
        state = await store.initialize(session_id, total_questions=5, max_follow_up=2)
        await session.commit()

    assert state.status is FlowStatus.INIT
    assert state.version == 1

    async with factory() as session:
        store = FlowStateStore(session)
        updated = await store.mutate(
            session_id, lambda current: current.model_copy(update={"status": FlowStatus.ASKING})
        )
        await session.commit()

    assert updated.status is FlowStatus.ASKING
    assert updated.version == 2


async def test_mutate_rejects_illegal_transition(factory, session_id: str) -> None:
    async with factory() as session:
        store = FlowStateStore(session)
        await store.initialize(session_id, total_questions=3, max_follow_up=1)
        await session.commit()

    async with factory() as session:
        store = FlowStateStore(session)
        with pytest.raises(IllegalFlowTransition):
            await store.mutate(
                session_id,
                lambda current: current.model_copy(update={"status": FlowStatus.EVALUATING}),
            )


async def test_same_status_mutation_is_allowed(factory, session_id: str) -> None:
    async with factory() as session:
        store = FlowStateStore(session)
        await store.initialize(session_id, total_questions=3, max_follow_up=1)
        await session.commit()

    async with factory() as session:
        store = FlowStateStore(session)
        updated = await store.mutate(
            session_id, lambda current: current.model_copy(update={"current_index": 2})
        )
        await session.commit()

    assert updated.current_index == 2


async def test_concurrent_mutations_all_land(factory, session_id: str) -> None:
    async with factory() as session:
        await FlowStateStore(session).initialize(session_id, total_questions=5, max_follow_up=2)
        await session.commit()

    async def bump() -> int:
        async with factory() as session:
            store = FlowStateStore(session)
            state = await store.mutate(
                session_id,
                lambda current: current.model_copy(
                    update={"current_index": current.current_index + 1}
                ),
            )
            await session.commit()
            return state.current_index

    indexes = await asyncio.gather(*(bump() for _ in range(10)))

    assert sorted(indexes) == list(range(1, 11))

    async with factory() as session:
        stored = await FlowStateStore(session).load(session_id)
    assert stored is not None
    assert stored.current_index == 10
    assert stored.version == 11  # 1 initial + 10 successful CAS updates
