"""T2: session repository behaviour (create / supersede / transition / idempotency constraint)."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from better_resume.interview_engine.errors import IllegalSessionTransition, SessionNotFound
from better_resume.interview_engine.session_fsm import SessionStatus
from better_resume.interview_engine.session_repo import InterviewSessionRepository


@pytest.fixture
async def factory(migrated_database: str):
    engine = create_async_engine(migrated_database, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    yield session_factory
    await engine.dispose()


async def test_create_starts_in_draft(factory) -> None:
    async with factory() as session:
        created = await InterviewSessionRepository(session).create(user_id="u1")
        await session.commit()

    assert created.status is SessionStatus.DRAFT
    assert created.user_id == "u1"
    assert created.finished_at is None


async def test_transition_follows_the_fsm(factory) -> None:
    async with factory() as session:
        repo = InterviewSessionRepository(session)
        created = await repo.create(user_id="u1")
        await session.commit()

    async with factory() as session:
        repo = InterviewSessionRepository(session)
        uploaded = await repo.transition(created.id, SessionStatus.RESUME_UPLOADING)
        ready = await repo.transition(created.id, SessionStatus.READY)
        await session.commit()

    assert uploaded.status is SessionStatus.RESUME_UPLOADING
    assert ready.status is SessionStatus.READY

    async with factory() as session:
        repo = InterviewSessionRepository(session)
        with pytest.raises(IllegalSessionTransition):
            await repo.transition(created.id, SessionStatus.DRAFT)  # ready -> draft is illegal


async def test_same_status_transition_is_idempotent(factory) -> None:
    async with factory() as session:
        repo = InterviewSessionRepository(session)
        created = await repo.create(user_id="u1")
        again = await repo.transition(created.id, SessionStatus.DRAFT)
        await session.commit()

    assert again.status is SessionStatus.DRAFT


async def test_new_session_supersedes_active_ones(factory) -> None:
    async with factory() as session:
        repo = InterviewSessionRepository(session)
        first = await repo.create(user_id="u-super")
        await session.commit()

    async with factory() as session:
        repo = InterviewSessionRepository(session)
        await repo.transition(first.id, SessionStatus.RESUME_UPLOADING)
        await repo.transition(first.id, SessionStatus.READY)
        await session.commit()

    async with factory() as session:
        repo = InterviewSessionRepository(session)
        second = await repo.create(user_id="u-super", supersede_active=True)
        await session.commit()

    async with factory() as session:
        repo = InterviewSessionRepository(session)
        old = await repo.get(first.id)
        active = await repo.list_active("u-super")
        await session.commit()

    assert old.status is SessionStatus.ABANDONED
    assert [item.id for item in active] == [second.id]


async def test_missing_session_raises(factory) -> None:
    async with factory() as session:
        repo = InterviewSessionRepository(session)
        with pytest.raises(SessionNotFound):
            await repo.get("00000000-0000-0000-0000-000000000000")


async def test_foreign_session_is_not_visible_to_other_user(factory) -> None:
    async with factory() as session:
        created = await InterviewSessionRepository(session).create(user_id="owner")
        await session.commit()

    async with factory() as session:
        repo = InterviewSessionRepository(session)
        with pytest.raises(SessionNotFound):
            await repo.get_for_user(created.id, "intruder")


async def test_answer_request_id_is_unique(factory) -> None:
    from better_resume.interview_engine.answer_repo import AnswerRepository

    async with factory() as session:
        created = await InterviewSessionRepository(session).create(user_id="u-uniq")
        await session.commit()

    async with factory() as session:
        repo = AnswerRepository(session)
        await repo.add(
            session_id=created.id,
            question_no="1",
            request_id="req-1",
            answer="第一个答案",
        )
        await session.commit()

    async with factory() as session:
        repo = AnswerRepository(session)
        with pytest.raises(IntegrityError):
            await repo.add(
                session_id=created.id,
                question_no="1",
                request_id="req-1",
                answer="重复投递",
            )
            await session.commit()
