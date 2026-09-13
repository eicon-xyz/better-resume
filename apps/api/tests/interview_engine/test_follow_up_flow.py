"""T5: follow-ups are generated, numbered and routed back to the main question."""

from __future__ import annotations

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
    QuestionService,
)
from better_resume.interview_engine.evaluation import ScoreResult
from better_resume.interview_engine.orm import InterviewQuestionRow
from better_resume.llm_gateway import ChatRequest, ChatResult, LlmTimeoutError, StreamEvent

from .test_parser_helpers import build_resume_pdf

USER = "u-followup"


class FakeGateway:
    """Returns question batches, scores and follow-up questions, in that order of asking."""

    def __init__(
        self, *, scores: list[ScoreResult] | None = None, fail_follow_up: bool = False
    ) -> None:
        self._scores = list(scores or [])
        self._fail_follow_up = fail_follow_up
        self.calls = 0

    async def complete(self, req: ChatRequest) -> ChatResult:
        self.calls += 1
        schema = req.response_schema
        if schema is QuestionBatch:
            batch = QuestionBatch(
                questions=[
                    {"topic": f"T{i}", "focus_points": [f"F{i}"], "text": f"第 {i} 题"}
                    for i in range(1, 4)
                ],
                resume_score=70.0,
            )
            return ChatResult(content=batch.model_dump_json(), model="m", parsed=batch)
        if schema is not None and schema.__name__ == "FollowUpQuestion":
            if self._fail_follow_up:
                raise LlmTimeoutError("follow-up writer down")
            payload = schema(text="能具体说说当时的取舍吗？")
            return ChatResult(content=payload.model_dump_json(), model="m", parsed=payload)
        score = self._scores.pop(0) if self._scores else ScoreResult(score=85, feedback="ok")
        return ChatResult(content=score.model_dump_json(), model="m", parsed=score)

    def stream(self, req: ChatRequest) -> AsyncIterator[StreamEvent]:  # pragma: no cover
        raise NotImplementedError


def low(score: float = 42.0, **kwargs: object) -> ScoreResult:
    return ScoreResult(score=score, feedback="不够深入", missing_points=["取舍"], **kwargs)  # type: ignore[arg-type]


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
    async with factory() as session:
        created = await InterviewSessionRepository(session).create(user_id=USER)
        await session.commit()
    await QuestionService(factory, resilience=DirectAiResilience()).generate(
        session_id=created.id,
        user_id=USER,
        resume_pdf=build_resume_pdf(),
        request_id="gen-f",
        gateway=FakeGateway(),
        count=3,
    )
    return created.id


def service(factory) -> AnswerService:
    return AnswerService(factory, resilience=DirectAiResilience())


async def test_low_score_triggers_a_follow_up(factory, ready_session: str) -> None:
    result = await service(factory).submit(
        session_id=ready_session,
        user_id=USER,
        question_no="1",
        answer="答得很浅",
        request_id="f-1",
        gateway=FakeGateway(scores=[low()]),
    )

    assert result.next_action == "follow_up"
    assert result.next_question_no == "1-F1"
    assert result.answer.follow_up_reason == "LOW_SCORE"
    assert result.answer.rule_version
    assert result.flow.status is FlowStatus.FOLLOW_UP
    assert result.flow.follow_up_count == 1

    async with factory() as session:
        rows = (
            (
                await session.execute(
                    select(InterviewQuestionRow).order_by(InterviewQuestionRow.topic_no)
                )
            )
            .scalars()
            .all()
        )
    follow_up = [row for row in rows if row.question_no == "1-F1"]
    assert len(follow_up) == 1
    assert follow_up[0].follow_up_index == 1
    assert follow_up[0].topic_no == 1
    assert follow_up[0].text == "能具体说说当时的取舍吗？"


async def test_answering_the_follow_up_returns_to_the_next_main_question(
    factory, ready_session: str
) -> None:
    svc = service(factory)
    await svc.submit(
        session_id=ready_session,
        user_id=USER,
        question_no="1",
        answer="浅",
        request_id="f-2a",
        gateway=FakeGateway(scores=[low()]),
    )

    result = await svc.submit(
        session_id=ready_session,
        user_id=USER,
        question_no="1-F1",
        answer="补充了取舍",
        request_id="f-2b",
        gateway=FakeGateway(scores=[ScoreResult(score=90, feedback="好")]),
    )

    assert result.next_action == "next_question"
    assert result.next_question_no == "2"
    assert result.flow.status is FlowStatus.ASKING
    assert result.flow.follow_up_count == 0  # counter resets for the new topic


async def test_follow_up_limit_sends_the_candidate_to_the_next_question(
    factory, ready_session: str
) -> None:
    svc = service(factory)
    first = await svc.submit(
        session_id=ready_session,
        user_id=USER,
        question_no="1",
        answer="浅",
        request_id="f-3a",
        gateway=FakeGateway(scores=[low()]),
    )
    assert first.next_question_no == "1-F1"

    second = await svc.submit(
        session_id=ready_session,
        user_id=USER,
        question_no="1-F1",
        answer="还是浅",
        request_id="f-3b",
        gateway=FakeGateway(scores=[low()]),
    )
    assert second.next_question_no == "1-F2"

    third = await svc.submit(
        session_id=ready_session,
        user_id=USER,
        question_no="1-F2",
        answer="依然浅",
        request_id="f-3c",
        gateway=FakeGateway(scores=[low()]),
    )

    assert third.answer.follow_up_reason == "FOLLOW_UP_LIMIT_REACHED"
    assert third.next_action == "next_question"
    assert third.next_question_no == "2"
    assert third.flow.status is FlowStatus.ASKING


async def test_model_suggestion_triggers_a_follow_up_even_with_a_good_score(
    factory, ready_session: str
) -> None:
    result = await service(factory).submit(
        session_id=ready_session,
        user_id=USER,
        question_no="1",
        answer="还行",
        request_id="f-4",
        gateway=FakeGateway(scores=[ScoreResult(score=88, feedback="不错", follow_up_needed=True)]),
    )

    assert result.next_action == "follow_up"
    assert result.answer.follow_up_reason == "AI_SUGGESTED"


async def test_missing_points_alone_trigger_a_follow_up(factory, ready_session: str) -> None:
    result = await service(factory).submit(
        session_id=ready_session,
        user_id=USER,
        question_no="1",
        answer="没提量化",
        request_id="f-5",
        gateway=FakeGateway(
            scores=[ScoreResult(score=80, feedback="还行", missing_points=["量化结果"])]
        ),
    )

    assert result.next_action == "follow_up"
    assert result.answer.follow_up_reason == "MISSING_POINTS"


async def test_follow_up_writer_failure_keeps_the_turn_retryable(
    factory, ready_session: str
) -> None:
    with pytest.raises(LlmTimeoutError):
        await service(factory).submit(
            session_id=ready_session,
            user_id=USER,
            question_no="1",
            answer="浅",
            request_id="f-6",
            gateway=FakeGateway(scores=[low()], fail_follow_up=True),
        )

    async with factory() as session:
        flow = await FlowStateStore(session).load(ready_session)
        questions = (await session.execute(select(InterviewQuestionRow))).scalars().all()

    assert flow is not None
    assert flow.status is FlowStatus.ASKING
    assert flow.current_question_no == "1"
    assert [row.question_no for row in questions] == ["1", "2", "3"]  # no half-written follow-up
