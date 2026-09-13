"""T4: answer/evaluation pipeline — idempotent, question-locked, rollback on failure."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from better_resume.ai_resilience import DirectAiResilience
from better_resume.interview_engine import (
    AnswerService,
    FlowStateStore,
    FlowStatus,
    InterviewSessionRepository,
    QuestionBatch,
    QuestionLockRegistry,
    QuestionService,
    SessionStatus,
)
from better_resume.interview_engine.errors import (
    IllegalSessionTransition,
    QuestionNotCurrent,
)
from better_resume.interview_engine.evaluation import ScoreResult
from better_resume.interview_engine.orm import InterviewAnswerRow
from better_resume.llm_gateway import (
    ChatRequest,
    ChatResult,
    LlmTimeoutError,
    StreamEvent,
)

from .test_parser_helpers import build_resume_pdf

USER = "u-answer"


class FakeGateway:
    """Vendor boundary only: returns queued scores or raises a queued error."""

    def __init__(
        self,
        scores: list[ScoreResult] | None = None,
        *,
        error: Exception | None = None,
        delay: float = 0.0,
        batch: QuestionBatch | None = None,
    ) -> None:
        self._scores = list(scores or [ScoreResult(score=80, feedback="不错")])
        self._batch = batch or make_batch(3)
        self._error = error
        self._delay = delay
        self.calls = 0

    async def complete(self, req: ChatRequest) -> ChatResult:
        self.calls += 1
        if self._delay:
            await asyncio.sleep(self._delay)
        if self._error is not None:
            raise self._error
        # Mirror the real adapter: answer the schema the caller asked for.
        if req.response_schema is QuestionBatch:
            return ChatResult(
                content=self._batch.model_dump_json(), model="deepseek-flash", parsed=self._batch
            )
        score = self._scores.pop(0) if len(self._scores) > 1 else self._scores[0]
        return ChatResult(
            content=score.model_dump_json(),
            model="deepseek-flash",
            parsed=score if req.response_schema else None,
        )

    def stream(self, req: ChatRequest) -> AsyncIterator[StreamEvent]:  # pragma: no cover
        raise NotImplementedError


def make_batch(count: int = 3) -> QuestionBatch:
    return QuestionBatch(
        questions=[
            {"topic": f"T{i}", "focus_points": [f"F{i}"], "text": f"第 {i} 题"}
            for i in range(1, count + 1)
        ],
        resume_score=70.0,
    )


@pytest.fixture
async def factory(migrated_database: str):
    engine = create_async_engine(migrated_database, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        await session.execute(
            text(
                "TRUNCATE interview_sessions, interview_questions, "
                "interview_answers, interview_flow_state CASCADE"
            )
        )
        await session.commit()
    yield session_factory
    await engine.dispose()


@pytest.fixture
async def ready_session(factory) -> str:
    """A session with 3 questions and flow status asking on question '1'."""
    async with factory() as session:
        created = await InterviewSessionRepository(session).create(user_id=USER)
        await session.commit()

    await QuestionService(factory, resilience=DirectAiResilience()).generate(
        session_id=created.id,
        user_id=USER,
        resume_pdf=build_resume_pdf(),
        request_id="gen-1",
        gateway=FakeGateway(),  # type: ignore[arg-type]
        count=3,
    )
    return created.id


def service(factory, *, locks: QuestionLockRegistry | None = None) -> AnswerService:
    return AnswerService(factory, resilience=DirectAiResilience(), locks=locks)


async def test_answer_is_scored_and_flow_advances(factory, ready_session: str) -> None:
    gateway = FakeGateway(
        # Passing score, no missing points: the T5 chain finds no reason to follow up.
        [ScoreResult(score=88.5, feedback="结构清晰")]
    )

    result = await service(factory).submit(
        session_id=ready_session,
        user_id=USER,
        question_no="1",
        answer="我负责了后端重构",
        request_id="ans-1",
        gateway=gateway,
    )

    assert result.replayed is False
    assert result.answer.score == 88.5
    assert result.answer.feedback == "结构清晰"
    assert result.answer.missing_points == []
    assert result.next_action == "next_question"
    assert result.flow.status is FlowStatus.ASKING
    assert result.flow.current_question_no == "2"
    assert result.session.status is SessionStatus.IN_PROGRESS
    assert result.session.started_at is not None


async def test_last_question_completes_the_flow(factory, ready_session: str) -> None:
    svc = service(factory)
    for index in (1, 2):
        await svc.submit(
            session_id=ready_session,
            user_id=USER,
            question_no=str(index),
            answer=f"答案{index}",
            request_id=f"ans-last-{index}",
            gateway=FakeGateway(),
        )

    final = await svc.submit(
        session_id=ready_session,
        user_id=USER,
        question_no="3",
        answer="最后一题",
        request_id="ans-last-3",
        gateway=FakeGateway(),
    )

    assert final.next_action == "finished"
    assert final.flow.status is FlowStatus.COMPLETED
    assert final.flow.current_question_no is None


async def test_duplicate_request_replays_without_recharging(factory, ready_session: str) -> None:
    svc = service(factory)
    gateway = FakeGateway()
    first = await svc.submit(
        session_id=ready_session,
        user_id=USER,
        question_no="1",
        answer="第一次",
        request_id="ans-dup",
        gateway=gateway,
    )

    replay = await svc.submit(
        session_id=ready_session,
        user_id=USER,
        question_no="1",
        answer="第一次",
        request_id="ans-dup",
        gateway=FakeGateway(),
    )

    assert replay.replayed is True
    assert replay.answer.id == first.answer.id
    assert gateway.calls == 1


async def test_concurrent_answers_for_one_question_are_serialised(
    factory, ready_session: str
) -> None:
    svc = service(factory)
    gateway = FakeGateway(delay=0.05)

    async def answer(index: int):
        return await svc.submit(
            session_id=ready_session,
            user_id=USER,
            question_no="1",
            answer=f"并发答案{index}",
            request_id=f"ans-race-{index}",
            gateway=gateway,
        )

    results = await asyncio.gather(*(answer(i) for i in range(10)), return_exceptions=True)
    successes = [r for r in results if not isinstance(r, Exception)]

    assert gateway.calls == 1  # only the winner reached the vendor
    assert len(successes) == 1

    async with factory() as session:
        rows = (await session.execute(select(InterviewAnswerRow))).scalars().all()
    assert len(rows) == 1


async def test_scoring_failure_keeps_the_question_answerable(factory, ready_session: str) -> None:
    svc = service(factory)
    failing = FakeGateway(error=LlmTimeoutError("scorer down"))

    with pytest.raises(LlmTimeoutError):
        await svc.submit(
            session_id=ready_session,
            user_id=USER,
            question_no="1",
            answer="会失败的答案",
            request_id="ans-fail",
            gateway=failing,
        )

    async with factory() as session:
        flow = await FlowStateStore(session).load(ready_session)
        rows = (await session.execute(select(InterviewAnswerRow))).scalars().all()
        stored = await InterviewSessionRepository(session).get(ready_session)

    assert flow is not None
    assert flow.status is FlowStatus.ASKING  # rolled back
    assert flow.current_question_no == "1"
    assert len(rows) == 1
    assert rows[0].error_message
    assert rows[0].score is None
    assert stored.status is SessionStatus.IN_PROGRESS

    retry = await svc.submit(
        session_id=ready_session,
        user_id=USER,
        question_no="1",
        answer="会失败的答案",
        request_id="ans-fail-retry",
        gateway=FakeGateway(),
    )
    assert retry.answer.score == 80
    assert retry.next_action == "next_question"


async def test_answering_another_question_is_rejected(factory, ready_session: str) -> None:
    with pytest.raises(QuestionNotCurrent):
        await service(factory).submit(
            session_id=ready_session,
            user_id=USER,
            question_no="2",
            answer="抢答",
            request_id="ans-wrong",
            gateway=FakeGateway(),
        )


async def test_answering_a_finished_session_is_rejected(factory, ready_session: str) -> None:
    svc = service(factory)
    for index in (1, 2, 3):
        await svc.submit(
            session_id=ready_session,
            user_id=USER,
            question_no=str(index),
            answer=f"答案{index}",
            request_id=f"ans-fin-{index}",
            gateway=FakeGateway(),
        )

    async with factory() as session:
        await InterviewSessionRepository(session).transition(ready_session, SessionStatus.FINISHED)
        await session.commit()

    with pytest.raises(IllegalSessionTransition):
        await svc.submit(
            session_id=ready_session,
            user_id=USER,
            question_no="3",
            answer="再答一次",
            request_id="ans-after-finish",
            gateway=FakeGateway(),
        )


async def test_unknown_question_number_is_rejected(factory, ready_session: str) -> None:
    from better_resume.interview_engine.errors import QuestionNotFound

    with pytest.raises(QuestionNotFound):
        await service(factory).submit(
            session_id=ready_session,
            user_id=USER,
            question_no="99",
            answer="不存在",
            request_id="ans-ghost",
            gateway=FakeGateway(),
        )


async def test_lock_registry_releases_entries(factory, ready_session: str) -> None:
    locks = QuestionLockRegistry()

    await service(factory, locks=locks).submit(
        session_id=ready_session,
        user_id=USER,
        question_no="1",
        answer="答案",
        request_id="ans-lock",
        gateway=FakeGateway(),
    )

    assert locks.active_keys() == []
