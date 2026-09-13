"""T6: restore (with derivation), idempotent finish and the frozen report snapshot."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy import delete, select, text
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
    ReportService,
    RestoreService,
    SessionStatus,
)
from better_resume.interview_engine.errors import SessionNotFound
from better_resume.interview_engine.evaluation import ScoreResult
from better_resume.interview_engine.orm import InterviewFlowStateRow, InterviewReportRow
from better_resume.llm_gateway import ChatRequest, ChatResult, LlmTimeoutError, StreamEvent

from .test_parser_helpers import build_resume_pdf

USER = "u-report"


class FakeGateway:
    def __init__(
        self, *, scores: list[ScoreResult] | None = None, summary_error: Exception | None = None
    ) -> None:
        self._scores = list(scores or [])
        self._summary_error = summary_error
        self.summary_calls = 0

    async def complete(self, req: ChatRequest) -> ChatResult:
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
        name = schema.__name__ if schema is not None else ""
        if name == "FollowUpQuestion":
            payload = schema(text="能具体说说取舍吗？")
            return ChatResult(content=payload.model_dump_json(), model="m", parsed=payload)
        if name == "ReportSummary":
            self.summary_calls += 1
            if self._summary_error is not None:
                raise self._summary_error
            payload = schema(summary="候选人基础扎实，项目细节还可再深挖。")
            return ChatResult(content=payload.model_dump_json(), model="m", parsed=payload)
        score = self._scores.pop(0) if self._scores else ScoreResult(score=80, feedback="ok")
        return ChatResult(content=score.model_dump_json(), model="m", parsed=score)

    def stream(self, req: ChatRequest) -> AsyncIterator[StreamEvent]:  # pragma: no cover
        raise NotImplementedError


@pytest.fixture
async def factory(migrated_database: str):
    engine = create_async_engine(migrated_database, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        await session.execute(
            text(
                "TRUNCATE interview_sessions, interview_questions, interview_answers, "
                "interview_flow_state, interview_reports CASCADE"
            )
        )
        await session.commit()
    yield session_factory
    await engine.dispose()


async def make_session(
    factory, *, answers: int = 0, scores: list[ScoreResult] | None = None
) -> str:
    async with factory() as session:
        created = await InterviewSessionRepository(session).create(user_id=USER)
        await session.commit()

    await QuestionService(factory, resilience=DirectAiResilience()).generate(
        session_id=created.id,
        user_id=USER,
        resume_pdf=build_resume_pdf(),
        request_id="gen-r",
        gateway=FakeGateway(),
        count=3,
    )

    answers_service = AnswerService(factory, resilience=DirectAiResilience())
    for index in range(answers):
        # Always answer whatever the flow currently asks (a low score may insert a follow-up).
        async with factory() as db:
            flow = await FlowStateStore(db).load(created.id)
        question_no = flow.current_question_no if flow is not None else None
        assert question_no is not None
        score = (scores or [])[index] if scores and index < len(scores) else None
        await answers_service.submit(
            session_id=created.id,
            user_id=USER,
            question_no=question_no,
            answer=f"第 {index + 1} 题的回答",
            request_id=f"ans-{index + 1}",
            gateway=FakeGateway(scores=[score] if score else None),
        )
    return created.id


async def test_restore_reports_progress_and_current_question(factory) -> None:
    session_id = await make_session(factory, answers=1)

    view = await RestoreService(factory).restore(session_id=session_id, user_id=USER)

    assert view.derived is False
    assert view.session.status is SessionStatus.IN_PROGRESS
    assert view.flow_status is FlowStatus.ASKING
    assert view.current_question_no == "2"
    assert view.current_question is not None
    assert view.current_question.text == "第 2 题"
    assert view.answered == 1
    assert view.total_questions == 3
    assert view.last_result is not None
    assert view.last_result.score == 80


async def test_restore_works_before_any_answer(factory) -> None:
    session_id = await make_session(factory, answers=0)

    view = await RestoreService(factory).restore(session_id=session_id, user_id=USER)

    assert view.session.status is SessionStatus.READY
    assert view.current_question_no == "1"
    assert view.answered == 0
    assert view.last_result is None


async def test_restore_derives_flow_state_when_the_row_is_gone(factory) -> None:
    session_id = await make_session(factory, answers=2)

    async with factory() as session:  # simulate a wiped Redis/hot state
        await session.execute(
            delete(InterviewFlowStateRow).where(InterviewFlowStateRow.session_id == session_id)
        )
        await session.commit()

    view = await RestoreService(factory).restore(session_id=session_id, user_id=USER)

    assert view.derived is True
    assert view.current_question_no == "3"
    assert view.answered == 2

    async with factory() as session:
        restored = await FlowStateStore(session).load(session_id)
    assert restored is not None  # derived state was written back
    assert restored.current_question_no == "3"


async def test_restore_marks_a_fully_answered_session_completed(factory) -> None:
    session_id = await make_session(factory, answers=3)

    view = await RestoreService(factory).restore(session_id=session_id, user_id=USER)

    assert view.flow_status is FlowStatus.COMPLETED
    assert view.current_question_no is None
    assert view.answered == 3


async def test_restore_hides_other_users_sessions(factory) -> None:
    session_id = await make_session(factory, answers=0)

    with pytest.raises(SessionNotFound):
        await RestoreService(factory).restore(session_id=session_id, user_id="intruder")


async def test_finish_builds_a_report_and_is_idempotent(factory) -> None:
    # No missing points and passing scores: three clean main answers, no follow-ups.
    scores = [
        ScoreResult(score=90, feedback="好"),
        ScoreResult(score=80, feedback="不错"),
        ScoreResult(score=70, feedback="中"),
    ]
    session_id = await make_session(factory, answers=3, scores=scores)
    service = ReportService(factory, resilience=DirectAiResilience())

    first = await service.finish(session_id=session_id, user_id=USER, gateway=FakeGateway())
    second = await service.finish(
        session_id=session_id,
        user_id=USER,
        gateway=FakeGateway(summary_error=LlmTimeoutError("boom")),
    )

    assert first.session.status is SessionStatus.FINISHED
    assert first.session.finished_at is not None
    assert second.session.finished_at == first.session.finished_at
    assert second.report.payload == first.report.payload  # frozen snapshot

    async with factory() as session:
        rows = (await session.execute(select(InterviewReportRow))).scalars().all()
    assert len(rows) == 1

    assert first.report.overall_score == pytest.approx(80.0, abs=0.1)
    dimensions = {item["key"]: item["score"] for item in first.report.dimensions}
    assert set(dimensions) == {"accuracy", "depth", "coverage", "completeness"}
    assert dimensions["accuracy"] == pytest.approx(80.0, abs=0.1)  # main-question mean
    assert dimensions["depth"] == pytest.approx(80.0, abs=0.1)  # no follow-ups: reuse accuracy
    assert dimensions["completeness"] == pytest.approx(100.0, abs=0.1)
    assert 0 <= dimensions["coverage"] <= 100
    assert first.report.summary  # LLM summary present on the first call


async def test_finish_survives_a_summary_failure(factory) -> None:
    session_id = await make_session(factory, answers=3)
    service = ReportService(factory, resilience=DirectAiResilience())

    result = await service.finish(
        session_id=session_id,
        user_id=USER,
        gateway=FakeGateway(summary_error=LlmTimeoutError("summariser down")),
    )

    assert result.report.summary is None
    assert result.llm_summary_used is False
    assert result.report.overall_score is not None  # numbers never depend on the LLM
    assert len(result.report.turns) == 3


async def test_report_turns_replay_every_question_in_order(factory) -> None:
    scores = [ScoreResult(score=42, feedback="浅", missing_points=["取舍"])]
    session_id = await make_session(factory, answers=1, scores=scores)
    service = ReportService(factory, resilience=DirectAiResilience())

    result = await service.finish(session_id=session_id, user_id=USER, gateway=FakeGateway())

    questions = [turn["question_no"] for turn in result.report.turns]  # type: ignore[union-attr]
    assert questions[0] == "1"
    assert "1-F1" in questions  # the follow-up triggered by the low score is part of the replay
    assert result.report.turns[0]["score"] == 42
    assert result.report.turns[0]["missing_points"] == ["取舍"]


async def test_report_is_missing_before_finish(factory) -> None:
    session_id = await make_session(factory, answers=1)
    service = ReportService(factory, resilience=DirectAiResilience())

    with pytest.raises(SessionNotFound):
        await service.get_report(session_id=session_id, user_id=USER)
