"""T3: question generation — schema-validated, idempotent, no half-written state."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from better_resume.ai_resilience import DirectAiResilience
from better_resume.interview_engine import (
    InterviewSessionRepository,
    QuestionService,
    SessionStatus,
)
from better_resume.interview_engine.errors import IllegalSessionTransition
from better_resume.interview_engine.orm import InterviewFlowStateRow, InterviewQuestionRow
from better_resume.interview_engine.prompts import QuestionBatch
from better_resume.llm_gateway import (
    ChatRequest,
    ChatResult,
    LlmSchemaError,
    LlmTimeoutError,
    StreamEvent,
)

from .test_parser_helpers import build_resume_pdf

USER = "u-question"


class FakeGateway:
    """Only the vendor boundary is faked; Pydantic validation still runs for real."""

    def __init__(
        self, batch: QuestionBatch | None = None, *, error: Exception | None = None
    ) -> None:
        self._batch = batch
        self._error = error
        self.requests: list[ChatRequest] = []

    async def complete(self, req: ChatRequest) -> ChatResult:
        self.requests.append(req)
        if self._error is not None:
            raise self._error
        assert self._batch is not None
        content = self._batch.model_dump_json()
        # Mirror the real adapter: response_schema requests come back validated as \`parsed\`.
        parsed = type(self._batch).model_validate_json(content) if req.response_schema else None
        return ChatResult(content=content, model="deepseek-flash", parsed=parsed)

    def stream(self, req: ChatRequest) -> AsyncIterator[StreamEvent]:  # pragma: no cover
        raise NotImplementedError


def make_batch(count: int = 5) -> QuestionBatch:
    return QuestionBatch(
        questions=[
            {
                "topic": f"主题{i}",
                "focus_points": [f"要点{i}A", f"要点{i}B"],
                "text": f"第 {i} 题：请说明你在项目中的做法",
            }
            for i in range(1, count + 1)
        ],
        resume_score=82.5,
        suggestions=["补充量化结果", "突出个人贡献"],
    )


@pytest.fixture
async def factory(migrated_database: str):
    engine = create_async_engine(migrated_database, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        await session.execute(
            text("TRUNCATE interview_sessions, interview_questions, interview_flow_state CASCADE")
        )
        await session.commit()
    yield session_factory
    await engine.dispose()


@pytest.fixture
async def session_id(factory) -> str:
    async with factory() as session:
        created = await InterviewSessionRepository(session).create(user_id=USER)
        await session.commit()
        return created.id


def service(factory) -> QuestionService:
    return QuestionService(factory, resilience=DirectAiResilience())


async def test_generation_persists_questions_and_readies_the_session(
    factory, session_id: str
) -> None:
    gateway = FakeGateway(make_batch(5))

    result = await service(factory).generate(
        session_id=session_id,
        user_id=USER,
        resume_pdf=build_resume_pdf(),
        request_id="req-gen-1",
        count=5,
        gateway=gateway,
    )

    assert result.replayed is False
    assert len(result.questions) == 5
    assert [q["question_no"] for q in result.questions] == ["1", "2", "3", "4", "5"]
    assert result.session.status is SessionStatus.READY
    assert result.session.question_count == 5
    assert result.session.resume_score == 82.5
    assert result.session.resume_sha256
    assert result.session.resume_path
    assert result.flow is not None
    assert result.flow.status.value == "asking"
    assert result.flow.current_question_no == "1"
    assert result.suggestions == ["补充量化结果", "突出个人贡献"]


async def test_focus_points_are_stored(factory, session_id: str) -> None:
    await service(factory).generate(
        session_id=session_id,
        user_id=USER,
        resume_pdf=build_resume_pdf(),
        request_id="req-gen-2",
        count=5,
        gateway=FakeGateway(make_batch(5)),
    )

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

    assert [row.focus_points for row in rows][:2] == [["要点1A", "要点1B"], ["要点2A", "要点2B"]]


async def test_schema_failure_leaves_no_half_state(factory, session_id: str) -> None:
    gateway = FakeGateway(error=LlmSchemaError("response does not match QuestionBatch"))

    with pytest.raises(LlmSchemaError):
        await service(factory).generate(
            session_id=session_id,
            user_id=USER,
            resume_pdf=build_resume_pdf(),
            request_id="req-gen-3",
            count=5,
            gateway=gateway,
        )

    async with factory() as session:
        questions = (await session.execute(select(InterviewQuestionRow))).scalars().all()
        flows = (await session.execute(select(InterviewFlowStateRow))).scalars().all()
        stored = await InterviewSessionRepository(session).get(session_id)

    assert questions == []
    assert flows == []
    assert stored.status is SessionStatus.DRAFT  # retryable
    assert stored.question_count == 0


async def test_repeat_call_replays_instead_of_regenerating(factory, session_id: str) -> None:
    first = service(factory)
    gateway = FakeGateway(make_batch(3))
    created = await first.generate(
        session_id=session_id,
        user_id=USER,
        resume_pdf=build_resume_pdf(),
        request_id="req-gen-4",
        count=3,
        gateway=gateway,
    )

    replay = await first.generate(
        session_id=session_id,
        user_id=USER,
        resume_pdf=build_resume_pdf(),
        request_id="req-gen-5",
        count=3,
        gateway=FakeGateway(make_batch(3)),
    )

    assert replay.replayed is True
    assert [q["question_no"] for q in replay.questions] == [
        q["question_no"] for q in created.questions
    ]
    assert len(gateway.requests) == 1  # the second call never reached the vendor


async def test_concurrent_generation_is_rejected_while_one_is_running(
    factory, session_id: str
) -> None:
    class SlowGateway(FakeGateway):
        def __init__(self) -> None:
            super().__init__(make_batch(5))
            self.started = asyncio.Event()
            self.release = asyncio.Event()

        async def complete(self, req: ChatRequest) -> ChatResult:
            self.requests.append(req)
            self.started.set()
            await self.release.wait()
            payload = make_batch(5)
            return ChatResult(
                content=payload.model_dump_json(),
                model="deepseek-flash",
                parsed=payload,
            )

    slow = SlowGateway()
    svc = service(factory)
    first = asyncio.create_task(
        svc.generate(
            session_id=session_id,
            user_id=USER,
            resume_pdf=build_resume_pdf(),
            request_id="req-gen-6",
            count=5,
            gateway=slow,
        )
    )
    await asyncio.wait_for(slow.started.wait(), timeout=5)

    with pytest.raises(IllegalSessionTransition):
        await svc.generate(
            session_id=session_id,
            user_id=USER,
            resume_pdf=build_resume_pdf(),
            request_id="req-gen-7",
            count=5,
            gateway=FakeGateway(make_batch(5)),
        )

    slow.release.set()
    await asyncio.wait_for(first, timeout=10)


async def test_vendor_failure_rolls_the_session_back_to_draft(factory, session_id: str) -> None:
    with pytest.raises(LlmTimeoutError):
        await service(factory).generate(
            session_id=session_id,
            user_id=USER,
            resume_pdf=build_resume_pdf(),
            request_id="req-gen-8",
            count=5,
            gateway=FakeGateway(error=LlmTimeoutError("upstream slow")),
        )

    async with factory() as session:
        stored = await InterviewSessionRepository(session).get(session_id)

    assert stored.status is SessionStatus.DRAFT


async def test_unparsable_resume_is_rejected_before_calling_the_vendor(
    factory, session_id: str
) -> None:
    from better_resume.resume_parser import ResumeParseError

    gateway = FakeGateway(make_batch(5))

    with pytest.raises(ResumeParseError):
        await service(factory).generate(
            session_id=session_id,
            user_id=USER,
            resume_pdf=b"not a pdf at all",
            request_id="req-gen-9",
            count=5,
            gateway=gateway,
        )

    assert gateway.requests == []
    async with factory() as session:
        stored = await InterviewSessionRepository(session).get(session_id)
    assert stored.status is SessionStatus.DRAFT


async def test_question_count_is_clamped(factory, session_id: str) -> None:
    gateway = FakeGateway(make_batch(10))

    result = await service(factory).generate(
        session_id=session_id,
        user_id=USER,
        resume_pdf=build_resume_pdf(),
        request_id="req-gen-10",
        count=99,
        gateway=gateway,
    )

    assert len(result.questions) == 10  # hard upper bound keeps the token budget sane
    prompt = gateway.requests[0].messages
    assert any("请出 10 道面试题" in message.content for message in prompt)
    assert all("99" not in message.content for message in prompt)


async def test_prompt_carries_resume_digest(factory, session_id: str) -> None:
    gateway = FakeGateway(make_batch(2))

    await service(factory).generate(
        session_id=session_id,
        user_id=USER,
        resume_pdf=build_resume_pdf(),
        request_id="req-gen-11",
        count=2,
        gateway=gateway,
    )

    contents = "\n".join(message.content for message in gateway.requests[0].messages)
    assert "张三" in contents or "Jane" in contents
    assert gateway.requests[0].response_schema is QuestionBatch
