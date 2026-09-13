"""M3-T8: the four AI links through the real guard chain — keys, dedupe, taxonomy.

Service-level concurrency tests use the real database and the real ResilientAiResilience:
only the vendor boundary is faked, exactly like the rest of the suite.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from better_resume.ai_resilience import (
    AiInvalid,
    ManualClock,
    ResilienceMetrics,
    ResilientAiResilience,
)
from better_resume.chat import ChatService, build_resilience_key
from better_resume.chat.models import Done
from better_resume.conversation import SessionRef, SqlConversationStore
from better_resume.interview_engine import (
    AnswerService,
    QuestionBatch,
    QuestionLockRegistry,
    QuestionService,
)
from better_resume.interview_engine.evaluation import ScoreResult
from better_resume.interview_engine.follow_up_service import build_follow_up_key
from better_resume.interview_engine.question_service import build_generation_key
from better_resume.interview_engine.report_service import build_report_key
from better_resume.interview_engine.session_repo import InterviewSessionRepository
from better_resume.llm_gateway import (
    ChatRequest,
    ChatResult,
    ContentDelta,
    LlmSchemaError,
    LlmTimeoutError,
    StreamEvent,
)
from better_resume.main import create_app
from better_resume.settings import ResilienceSettings, Settings

from .interview_engine.test_parser_helpers import build_resume_pdf

USER = "resilience-user"


# ---- keys: every input the prompt depends on must be in the key --------------------


def test_generation_key_covers_resume_count_and_language() -> None:
    base = build_generation_key("s", resume_digest="resume-1", count=5, language="zh")

    assert base == build_generation_key("s", resume_digest="resume-1", count=5, language="zh")
    assert base != build_generation_key("s", resume_digest="resume-2", count=5, language="zh")
    assert base != build_generation_key("s", resume_digest="resume-1", count=3, language="zh")
    assert base != build_generation_key("s", resume_digest="resume-1", count=5, language="en")
    assert base != build_generation_key("other", resume_digest="resume-1", count=5, language="zh")
    assert "resume-1" not in base  # only the digest travels


def test_follow_up_key_covers_the_answer() -> None:
    base = build_follow_up_key("s", "1", "我的答案")

    assert base == build_follow_up_key("s", "1", "我的答案")
    assert base != build_follow_up_key("s", "1", "另一个答案")
    assert base != build_follow_up_key("s", "2", "我的答案")
    assert "我的答案" not in base


def test_report_key_covers_the_numbers() -> None:
    payload = {
        "session_id": "s",
        "overall_score": 71.0,
        "dimensions": {"accuracy": 60.0},
        "turns": [{"missing_points": ["并发"]}],
    }

    base = build_report_key(payload)
    assert base == build_report_key(dict(payload))
    assert base != build_report_key({**payload, "overall_score": 72.0})
    assert base != build_report_key({**payload, "turns": [{"missing_points": []}]})
    assert base != build_report_key({**payload, "session_id": "other"})


def test_chat_key_covers_the_model() -> None:
    base = build_resilience_key("s", "同一句话", "deepseek-v3")

    assert base == build_resilience_key("s", "同一句话", "deepseek-v3")
    assert base != build_resilience_key("s", "同一句话", "deepseek-r1")
    assert base != build_resilience_key("s", "另一句话", "deepseek-v3")
    assert "同一句话" not in base


# ---- the chat link: concurrent identical streams share one vendor call -------------


class FakeStreamGateway:
    def __init__(self) -> None:
        self.calls = 0
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    def stream(self, req: ChatRequest) -> AsyncIterator[StreamEvent]:
        return self._stream(req)

    async def _stream(self, req: ChatRequest) -> AsyncIterator[StreamEvent]:
        self.calls += 1
        self.started.set()
        yield ContentDelta(text="你")
        await self.release.wait()  # keep the flight open while the follower joins
        yield ContentDelta(text="好")
        yield Done(finish_reason="stop")

    async def complete(self, req: ChatRequest) -> ChatResult:  # pragma: no cover - unused
        raise NotImplementedError


@pytest.fixture
async def store_factory(migrated_database: str):
    engine = create_async_engine(migrated_database, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await session.execute(text("TRUNCATE conversation_messages, conversations CASCADE"))
        await session.commit()
    yield factory
    await engine.dispose()


async def test_concurrent_identical_chat_streams_share_one_vendor_call(store_factory) -> None:
    async with store_factory() as session:
        conversation = await SqlConversationStore(session).create(
            kind="chat", user_id=USER, title="t"
        )
        await session.commit()
    ref = SessionRef(kind="chat", session_id=conversation.id)

    resilience = ResilientAiResilience(
        Settings(_env_file=None), clock=ManualClock(), metrics=ResilienceMetrics()
    )
    service = ChatService(store_factory, resilience=resilience)
    gateway = FakeStreamGateway()

    async def one_turn() -> str:
        answer = ""
        async for event in service.stream_reply(
            session=ref, user_id=USER, content="同一个问题", gateway=gateway
        ):
            if isinstance(event, ContentDelta):
                answer += event.text
        return answer

    leader = asyncio.create_task(one_turn())
    await asyncio.wait_for(gateway.started.wait(), timeout=5.0)  # the flight is open now
    follower = asyncio.create_task(one_turn())
    # The follower has DB work to do before it reaches the seam: poll the metric instead
    # of guessing how many event-loop turns that takes (see PROBLEMS P9).
    for _ in range(200):
        # Real (tiny) sleeps: the follower's DB round trips need the loop to poll sockets,
        # which sleep(0) alone never does.
        await asyncio.sleep(0.005)
        if resilience.metrics.snapshot()["singleflight_follower"] == 1:
            break
    assert resilience.metrics.snapshot()["singleflight_follower"] == 1
    gateway.release.set()

    assert await asyncio.gather(leader, follower) == ["你好", "你好"]
    assert gateway.calls == 1
    assert resilience.metrics.snapshot()["singleflight_follower"] == 1


# ---- the evaluation link: replay protects a rolled-back question -------------------


class FakeInterviewGateway:
    def __init__(self, *, error: Exception | None = None, delay: float = 0.0) -> None:
        self.calls = 0
        self._error = error
        self._delay = delay
        self._batch = QuestionBatch(
            questions=[
                {"topic": f"T{i}", "focus_points": [f"F{i}"], "text": f"第 {i} 题"}
                for i in range(1, 4)
            ],
            resume_score=70.0,
        )

    async def complete(self, req: ChatRequest) -> ChatResult:
        self.calls += 1
        if self._delay:
            await asyncio.sleep(self._delay)
        if self._error is not None:
            raise self._error
        if req.response_schema is QuestionBatch:
            return ChatResult(
                content=self._batch.model_dump_json(), model="deepseek-flash", parsed=self._batch
            )
        score = ScoreResult(score=80.0, feedback="还行")
        return ChatResult(content=score.model_dump_json(), model="deepseek-flash", parsed=score)

    def stream(self, req: ChatRequest) -> AsyncIterator[StreamEvent]:  # pragma: no cover
        raise NotImplementedError


@pytest.fixture
async def interview_factory(migrated_database: str):
    engine = create_async_engine(migrated_database, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await session.execute(
            text(
                "TRUNCATE interview_sessions, interview_questions, "
                "interview_answers, interview_flow_state CASCADE"
            )
        )
        await session.commit()
    yield factory
    await engine.dispose()


async def test_schema_failure_is_replayed_instead_of_recalling_the_vendor(
    interview_factory,
) -> None:
    resilience = ResilientAiResilience(
        Settings(_env_file=None), clock=ManualClock(), metrics=ResilienceMetrics()
    )
    async with interview_factory() as session:
        created = await InterviewSessionRepository(session).create(user_id=USER)
        await session.commit()

    await QuestionService(interview_factory, resilience=resilience).generate(
        session_id=created.id,
        user_id=USER,
        resume_pdf=build_resume_pdf(),
        request_id="gen-1",
        gateway=FakeInterviewGateway(),  # type: ignore[arg-type]
        count=3,
    )

    failing = FakeInterviewGateway(error=LlmSchemaError("vendor returned prose"))
    service = AnswerService(interview_factory, resilience=resilience, locks=QuestionLockRegistry())

    for attempt in range(2):
        with pytest.raises(AiInvalid):
            await service.submit(
                session_id=created.id,
                user_id=USER,
                question_no="1",
                answer="同一段回答",
                request_id=f"ans-{attempt}",
                gateway=failing,  # type: ignore[arg-type]
            )

    assert failing.calls == 1  # the second attempt replayed the negative cache


# ---- HTTP: the taxonomy reaches the client ----------------------------------------


def login(client: TestClient) -> str:
    user_id = f"resilience-{uuid.uuid4().hex[:8]}"
    assert client.post("/api/v1/auth/session", json={"user_id": user_id}).status_code == 200
    return user_id


def upload(client: TestClient, session_id: str):
    return client.post(
        f"/api/v1/interview/sessions/{session_id}/questions",
        files={"file": ("cv.pdf", build_resume_pdf(), "application/pdf")},
        data={"count": "5"},
    )


def build_client(settings: Settings, resilience: ResilienceSettings, fake: object) -> TestClient:
    app = create_app(settings.model_copy(update={"resilience": resilience}))
    client = TestClient(app)
    client.__enter__()
    app.state.llm_gateway_factory = lambda spec, api_key: fake
    return client


def test_open_breaker_sheds_load_without_calling_the_vendor(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BR_DEEPSEEK_API_KEY", "sk-test-not-real")
    gateway = FakeInterviewGateway(error=LlmTimeoutError("vendor down"))
    client = build_client(
        settings,
        ResilienceSettings(breaker_min_calls=1, breaker_window=2, breaker_open_seconds=30.0),
        gateway,
    )
    try:
        login(client)
        session_id = client.post("/api/v1/interview/sessions", json={}).json()["id"]

        first = upload(client, session_id)
        assert first.status_code == 504
        assert first.json()["kind"] == "timeout"
        assert gateway.calls == 1

        second = upload(client, session_id)
        assert second.status_code == 503
        assert second.json()["kind"] == "unavailable"
        assert second.headers["retry-after"] == "5"
        assert gateway.calls == 1  # short-circuited: the vendor is left alone
    finally:
        client.__exit__(None, None, None)


def test_slow_vendor_hits_the_deadline_and_returns_504(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BR_DEEPSEEK_API_KEY", "sk-test-not-real")
    gateway = FakeInterviewGateway(delay=0.4)
    client = build_client(settings, ResilienceSettings(extraction_timeout_seconds=0.05), gateway)
    try:
        login(client)
        session_id = client.post("/api/v1/interview/sessions", json={}).json()["id"]

        response = upload(client, session_id)

        assert response.status_code == 504
        assert response.json()["kind"] == "timeout"
    finally:
        client.__exit__(None, None, None)
