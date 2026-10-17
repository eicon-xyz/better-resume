"""T4: answer HTTP surface — scoring, replay, rollback and error mapping."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Callable

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from better_resume.interview_engine import FlowStateStore, FlowStatus
from better_resume.interview_engine.evaluation import ScoreResult
from better_resume.interview_engine.orm import InterviewFlowStateRow
from better_resume.interview_engine.prompts import QuestionBatch
from better_resume.llm_gateway import ChatRequest, ChatResult, LlmTimeoutError, StreamEvent

from .interview_engine.test_parser_helpers import build_resume_pdf


class FakeGateway:
    """Answers whichever schema the caller asked for (question batch or score)."""

    def __init__(
        self,
        *,
        error: Exception | None = None,
        score: float = 84.0,
        missing: list[str] | None = None,
        follow_up_needed: bool = False,
    ) -> None:
        self._error = error
        self._score = score
        self._missing = list(missing or [])
        self._follow_up_needed = follow_up_needed
        self.calls = 0
        self.batch = QuestionBatch(
            questions=[
                {"topic": f"T{i}", "focus_points": [f"F{i}"], "text": f"第 {i} 题"}
                for i in range(1, 4)
            ],
            resume_score=71.0,
        )

    async def complete(self, req: ChatRequest) -> ChatResult:
        self.calls += 1
        if self._error is not None:
            raise self._error
        if req.response_schema is QuestionBatch:
            return ChatResult(
                content=self.batch.model_dump_json(), model="deepseek-flash", parsed=self.batch
            )
        if req.response_schema is not None and req.response_schema.__name__ == "FollowUpQuestion":
            follow_up = req.response_schema(text="能具体说说当时的取舍吗？")
            return ChatResult(
                content=follow_up.model_dump_json(), model="deepseek-flash", parsed=follow_up
            )
        score = ScoreResult(
            score=self._score,
            feedback="回答到位",
            missing_points=self._missing,
            follow_up_needed=self._follow_up_needed,
        )
        return ChatResult(content=score.model_dump_json(), model="deepseek-flash", parsed=score)

    def stream(self, req: ChatRequest) -> AsyncIterator[StreamEvent]:  # pragma: no cover
        raise NotImplementedError


@pytest.fixture
def gateway(app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> Callable[[FakeGateway], FakeGateway]:
    monkeypatch.setenv("BR_DEEPSEEK_API_KEY", "sk-test-not-real")

    def install(fake: FakeGateway) -> FakeGateway:
        app.state.llm_gateway_factory = lambda spec, api_key: fake
        return fake

    return install


def login(client: TestClient) -> str:
    user_id = f"answer-api-{uuid.uuid4().hex[:8]}"
    assert client.post("/api/v1/auth/session", json={"user_id": user_id}).status_code == 200
    return user_id


def prepare(client: TestClient, fake: FakeGateway) -> str:
    """Create a session and generate 3 questions."""
    session_id = client.post("/api/v1/interview/sessions", json={}).json()["id"]
    response = client.post(
        f"/api/v1/interview/sessions/{session_id}/questions",
        files={"file": ("cv.pdf", build_resume_pdf(), "application/pdf")},
        data={"count": "3"},
    )
    assert response.status_code == 201, response.text
    return session_id


def answer(
    client: TestClient, session_id: str, question_no: str, request_id: str, text: str = "我的回答"
):
    return client.post(
        f"/api/v1/interview/sessions/{session_id}/answers",
        json={"question_no": question_no, "answer": text, "request_id": request_id},
    )


def test_answers_require_a_session(client: TestClient) -> None:
    response = client.post(
        "/api/v1/interview/sessions/whatever/answers",
        json={"question_no": "1", "answer": "x", "request_id": "r1"},
    )
    assert response.status_code == 401


def test_answer_is_scored_and_returns_the_next_question(
    client: TestClient, gateway, migrated_database: str
) -> None:
    login(client)
    fake = gateway(FakeGateway(score=91.5))
    session_id = prepare(client, fake)

    response = answer(client, session_id, "1", "ans-1")

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["answer"]["score"] == 91.5
    assert payload["answer"]["feedback"] == "回答到位"
    assert payload["answer"]["missing_points"] == []
    assert payload["next_action"] == "next_question"
    assert payload["next_question_no"] == "2"
    assert payload["next_question"]["text"] == "第 2 题"
    assert payload["flow"]["status"] == "asking"
    assert payload["session"]["status"] == "in_progress"
    assert payload["replayed"] is False


def test_finishing_the_last_question_completes_the_flow(
    client: TestClient, gateway, migrated_database: str
) -> None:
    login(client)
    fake = gateway(FakeGateway())
    session_id = prepare(client, fake)

    for index in (1, 2):
        assert answer(client, session_id, str(index), f"ans-{index}").status_code == 201

    final = answer(client, session_id, "3", "ans-3")

    assert final.status_code == 201
    assert final.json()["next_action"] == "finished"
    assert final.json()["flow"]["status"] == "completed"
    assert final.json()["next_question"] is None


def test_duplicate_request_replays(client: TestClient, gateway, migrated_database: str) -> None:
    login(client)
    fake = gateway(FakeGateway())
    session_id = prepare(client, fake)

    first = answer(client, session_id, "1", "ans-dup")
    replay = answer(client, session_id, "1", "ans-dup")

    assert first.status_code == 201
    assert replay.status_code == 201
    assert replay.json()["replayed"] is True
    assert replay.json()["answer"]["score"] == first.json()["answer"]["score"]
    assert fake.calls == 2  # one question batch + one score, never a second score


def test_vendor_timeout_is_504_and_stays_answerable(
    client: TestClient, app: FastAPI, gateway, migrated_database: str
) -> None:
    """M3 contract change: the guard chain reports taxonomy kinds (timeout -> 504)."""
    login(client)
    fake = gateway(FakeGateway())
    session_id = prepare(client, fake)

    gateway(FakeGateway(error=LlmTimeoutError("scorer down")))
    failed = answer(client, session_id, "1", "ans-fail")

    assert failed.status_code == 504
    assert failed.json()["kind"] == "timeout"

    gateway(FakeGateway(score=70.0, missing=[]))
    retried = answer(client, session_id, "1", "ans-fail-retry")

    assert retried.status_code == 201
    assert retried.json()["answer"]["score"] == 70.0
    assert retried.json()["next_question_no"] == "2"


def test_retrying_the_same_request_id_after_a_timeout_scores(
    client: TestClient, gateway, migrated_database: str
) -> None:
    """P8 / IE-01: the published contract tells clients to resend the same request_id when
    retrying (schema.d.ts: "resend it when retrying"), so the resend must score — not hand back
    the failed attempt with score=None and leave the question permanently ungraded."""
    login(client)
    fake = gateway(FakeGateway())
    session_id = prepare(client, fake)

    gateway(FakeGateway(error=LlmTimeoutError("scorer down")))
    failed = answer(client, session_id, "1", "ans-retry-same")

    assert failed.status_code == 504

    gateway(FakeGateway(score=70.0, missing=[]))
    retried = answer(client, session_id, "1", "ans-retry-same")

    assert retried.status_code == 201, retried.text
    assert retried.json()["replayed"] is False
    assert retried.json()["answer"]["score"] == 70.0
    assert retried.json()["next_question_no"] == "2"


def test_low_score_follow_up_is_surfaced(
    client: TestClient, gateway, migrated_database: str
) -> None:
    login(client)
    fake = gateway(FakeGateway(score=38.0, missing=[]))
    session_id = prepare(client, fake)

    payload = answer(client, session_id, "1", "答得很浅").json()

    assert payload["next_action"] == "follow_up"
    assert payload["next_question_no"] == "1-F1"
    assert payload["next_question"]["text"] == "能具体说说当时的取舍吗？"
    assert payload["answer"]["follow_up_needed"] is True
    assert payload["answer"]["follow_up_reason"] == "LOW_SCORE"
    assert payload["answer"]["rule_version"]
    assert payload["flow"]["status"] == "follow_up"
    assert payload["flow"]["follow_up_count"] == 1


def test_wrong_question_is_conflict(client: TestClient, gateway, migrated_database: str) -> None:
    login(client)
    fake = gateway(FakeGateway())
    session_id = prepare(client, fake)

    response = answer(client, session_id, "3", "ans-wrong")

    assert response.status_code == 409
    assert "not the current question" in response.json()["detail"]


def test_other_users_session_is_not_found(
    client: TestClient, gateway, migrated_database: str
) -> None:
    login(client)
    fake = gateway(FakeGateway())
    session_id = prepare(client, fake)

    login(client)  # different user
    response = answer(client, session_id, "1", "ans-intruder")

    assert response.status_code == 404


def wipe_flow_state(database_url: str, session_id: str) -> None:
    """Drop the flow row: the state T19's restore read path no longer rebuilds for us."""

    # Own engine + NullPool: the app's pooled connections belong to the TestClient loop.
    async def run() -> None:
        engine = create_async_engine(database_url, poolclass=NullPool)
        try:
            async with engine.begin() as conn:
                await conn.execute(
                    delete(InterviewFlowStateRow).where(
                        InterviewFlowStateRow.session_id == session_id
                    )
                )
        finally:
            await engine.dispose()

    asyncio.run(run())


def reinsert_flow_state(database_url: str, session_id: str, *, total_questions: int = 3) -> None:
    """Put the row back the way question generation leaves it, so answering can resume."""

    async def run() -> None:
        engine = create_async_engine(database_url, poolclass=NullPool)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as db:
                await FlowStateStore(db).initialize(
                    session_id,
                    total_questions=total_questions,
                    status=FlowStatus.ASKING,
                    current_question_no="1",
                )
                await db.commit()
        finally:
            await engine.dispose()

    asyncio.run(run())


def test_missing_flow_state_is_a_named_server_fault_and_recovers(
    client: TestClient, gateway, migrated_database: str
) -> None:
    """A vanished flow row is our own data fault: not 401 ("you never logged in") and not
    503 ("the dependency is down"). It must say which state is missing, never score silently,
    and answering works again once an operator puts the row back."""
    login(client)
    fake = gateway(FakeGateway(score=84.0))
    session_id = prepare(client, fake)

    wipe_flow_state(migrated_database, session_id)
    failed = answer(client, session_id, "1", "ans-no-flow")

    assert failed.status_code == 500, failed.text
    payload = failed.json()
    assert payload["kind"] == "flow_state_missing"
    assert session_id in payload["detail"]
    assert "flow state missing" in payload["detail"]
    assert fake.calls == 1  # the question batch only: the answer never reached scoring

    reinsert_flow_state(migrated_database, session_id)
    recovered = answer(client, session_id, "1", "ans-no-flow")

    assert recovered.status_code == 201, recovered.text
    assert recovered.json()["answer"]["score"] == 84.0
    assert recovered.json()["next_question_no"] == "2"
