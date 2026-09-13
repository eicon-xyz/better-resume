"""T4: answer HTTP surface — scoring, replay, rollback and error mapping."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from better_resume.interview_engine.evaluation import ScoreResult
from better_resume.interview_engine.prompts import QuestionBatch
from better_resume.llm_gateway import ChatRequest, ChatResult, LlmTimeoutError, StreamEvent

from .interview_engine.test_parser_helpers import build_resume_pdf


class FakeGateway:
    """Answers whichever schema the caller asked for (question batch or score)."""

    def __init__(self, *, error: Exception | None = None, score: float = 84.0) -> None:
        self._error = error
        self._score = score
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
        score = ScoreResult(score=self._score, feedback="回答到位", missing_points=["缺少量化"])
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
    assert payload["answer"]["missing_points"] == ["缺少量化"]
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


def test_vendor_failure_is_502_and_stays_answerable(
    client: TestClient, app: FastAPI, gateway, migrated_database: str
) -> None:
    login(client)
    fake = gateway(FakeGateway())
    session_id = prepare(client, fake)

    gateway(FakeGateway(error=LlmTimeoutError("scorer down")))
    failed = answer(client, session_id, "1", "ans-fail")

    assert failed.status_code == 502
    assert failed.json()["kind"] == "retryable"

    gateway(FakeGateway(score=70.0))
    retried = answer(client, session_id, "1", "ans-fail-retry")

    assert retried.status_code == 201
    assert retried.json()["answer"]["score"] == 70.0
    assert retried.json()["next_question_no"] == "2"


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
