"""T6: restore / finish / report HTTP surface."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Callable

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from better_resume.interview_engine.evaluation import ScoreResult
from better_resume.interview_engine.orm import InterviewFlowStateRow
from better_resume.interview_engine.prompts import QuestionBatch
from better_resume.llm_gateway import ChatRequest, ChatResult, LlmTimeoutError, StreamEvent

from .interview_engine.test_parser_helpers import build_resume_pdf


class FakeGateway:
    def __init__(self, *, score: float = 82.0, summary_error: Exception | None = None) -> None:
        self._score = score
        self._summary_error = summary_error

    async def complete(self, req: ChatRequest) -> ChatResult:
        schema = req.response_schema
        name = schema.__name__ if schema is not None else ""
        if schema is QuestionBatch:
            batch = QuestionBatch(
                questions=[
                    {"topic": f"T{i}", "focus_points": [f"F{i}"], "text": f"第 {i} 题"}
                    for i in range(1, 4)
                ],
                resume_score=68.0,
            )
            return ChatResult(content=batch.model_dump_json(), model="m", parsed=batch)
        if name == "FollowUpQuestion":
            payload = schema(text="再具体一点？")
            return ChatResult(content=payload.model_dump_json(), model="m", parsed=payload)
        if name == "ReportSummary":
            if self._summary_error is not None:
                raise self._summary_error
            payload = schema(summary="整体不错，细节可再展开。")
            return ChatResult(content=payload.model_dump_json(), model="m", parsed=payload)
        score = ScoreResult(score=self._score, feedback="还可以")
        return ChatResult(content=score.model_dump_json(), model="m", parsed=score)

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
    user_id = f"report-api-{uuid.uuid4().hex[:8]}"
    assert client.post("/api/v1/auth/session", json={"user_id": user_id}).status_code == 200
    return user_id


def prepare(client: TestClient, *, answers: int = 0) -> str:
    session_id = client.post("/api/v1/interview/sessions", json={}).json()["id"]
    generated = client.post(
        f"/api/v1/interview/sessions/{session_id}/questions",
        files={"file": ("cv.pdf", build_resume_pdf(), "application/pdf")},
        data={"count": "3"},
    )
    assert generated.status_code == 201, generated.text

    for index in range(answers):
        current = client.get(f"/api/v1/interview/sessions/{session_id}/restore").json()
        question_no = current["flow"]["current_question_no"]
        answered = client.post(
            f"/api/v1/interview/sessions/{session_id}/answers",
            json={
                "question_no": question_no,
                "answer": f"第 {index + 1} 轮回答",
                "request_id": f"r-{index}",
            },
        )
        assert answered.status_code == 201, answered.text
    return session_id


def test_restore_returns_progress(client: TestClient, gateway, migrated_database: str) -> None:
    login(client)
    gateway(FakeGateway())
    session_id = prepare(client, answers=1)

    response = client.get(f"/api/v1/interview/sessions/{session_id}/restore")

    assert response.status_code == 200
    payload = response.json()
    assert payload["derived"] is False
    assert payload["answered"] == 1
    assert payload["total_questions"] == 3
    assert payload["flow"]["current_question_no"] == "2"
    assert payload["current_question"]["text"] == "第 2 题"
    assert payload["last_answer"]["score"] == 82.0
    assert payload["session"]["status"] == "in_progress"


def test_restore_derives_when_flow_state_vanished(
    client: TestClient, app: FastAPI, gateway, migrated_database: str
) -> None:
    login(client)
    gateway(FakeGateway())
    session_id = prepare(client, answers=2)

    # Own engine + NullPool: the app's pooled connections belong to the TestClient loop.
    async def wipe() -> None:
        engine = create_async_engine(migrated_database, poolclass=NullPool)
        try:
            async with engine.begin() as conn:
                await conn.execute(
                    delete(InterviewFlowStateRow).where(
                        InterviewFlowStateRow.session_id == session_id
                    )
                )
        finally:
            await engine.dispose()

    asyncio.run(wipe())

    payload = client.get(f"/api/v1/interview/sessions/{session_id}/restore").json()

    assert payload["derived"] is True
    assert payload["flow"]["current_question_no"] == "3"
    assert payload["answered"] == 2


def test_finish_creates_the_report_and_is_idempotent(
    client: TestClient, gateway, migrated_database: str
) -> None:
    login(client)
    gateway(FakeGateway())
    session_id = prepare(client, answers=3)

    first = client.post(f"/api/v1/interview/sessions/{session_id}/finish")
    second = client.post(f"/api/v1/interview/sessions/{session_id}/finish")

    assert first.status_code == 201, first.text
    assert second.status_code == 201
    assert first.json()["session"]["status"] == "finished"
    assert first.json()["overall_score"] == 82.0
    assert [item["key"] for item in first.json()["dimensions"]] == [
        "accuracy",
        "depth",
        "coverage",
        "completeness",
    ]
    assert len(first.json()["turns"]) == 3
    assert first.json()["summary"] == "整体不错，细节可再展开。"
    assert second.json()["overall_score"] == first.json()["overall_score"]
    assert second.json()["turns"] == first.json()["turns"]


def test_finish_without_summary_still_returns_numbers(
    client: TestClient, gateway, migrated_database: str
) -> None:
    login(client)
    gateway(FakeGateway())
    session_id = prepare(client, answers=3)
    gateway(FakeGateway(summary_error=LlmTimeoutError("summary down")))

    response = client.post(f"/api/v1/interview/sessions/{session_id}/finish")

    assert response.status_code == 201
    assert response.json()["summary"] is None
    assert response.json()["llm_summary_used"] is False
    assert response.json()["overall_score"] == 82.0


def test_report_is_404_before_finish(client: TestClient, gateway, migrated_database: str) -> None:
    login(client)
    gateway(FakeGateway())
    session_id = prepare(client, answers=1)

    assert client.get(f"/api/v1/interview/sessions/{session_id}/report").status_code == 404


def test_report_available_after_finish(client: TestClient, gateway, migrated_database: str) -> None:
    login(client)
    gateway(FakeGateway())
    session_id = prepare(client, answers=3)
    client.post(f"/api/v1/interview/sessions/{session_id}/finish")

    response = client.get(f"/api/v1/interview/sessions/{session_id}/report")

    assert response.status_code == 200
    assert response.json()["overall_score"] == 82.0
    assert response.json()["suggestions"]


def test_other_users_report_is_not_found(
    client: TestClient, gateway, migrated_database: str
) -> None:
    login(client)
    gateway(FakeGateway())
    session_id = prepare(client, answers=3)
    client.post(f"/api/v1/interview/sessions/{session_id}/finish")

    login(client)
    assert client.get(f"/api/v1/interview/sessions/{session_id}/report").status_code == 404
    assert client.get(f"/api/v1/interview/sessions/{session_id}/restore").status_code == 404
