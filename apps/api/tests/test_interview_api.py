"""T3: interview HTTP surface — session lifecycle, resume upload and question generation."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from better_resume.interview_engine.prompts import QuestionBatch
from better_resume.llm_gateway import ChatRequest, ChatResult, LlmTimeoutError, StreamEvent

from .interview_engine.test_parser_helpers import build_resume_pdf


class FakeGateway:
    def __init__(
        self, batch: QuestionBatch | None = None, *, error: Exception | None = None
    ) -> None:
        self._batch = batch
        self._error = error
        self.calls = 0

    async def complete(self, req: ChatRequest) -> ChatResult:
        self.calls += 1
        if self._error is not None:
            raise self._error
        assert self._batch is not None
        content = self._batch.model_dump_json()
        parsed = type(self._batch).model_validate_json(content) if req.response_schema else None
        return ChatResult(content=content, model="deepseek-flash", parsed=parsed)

    def stream(self, req: ChatRequest) -> AsyncIterator[StreamEvent]:  # pragma: no cover
        raise NotImplementedError


def batch(count: int = 5) -> QuestionBatch:
    return QuestionBatch(
        questions=[
            {
                "topic": f"主题{i}",
                "focus_points": [f"要点{i}"],
                "text": f"第 {i} 题：请介绍你的项目",
            }
            for i in range(1, count + 1)
        ],
        resume_score=77.0,
        suggestions=["补充量化"],
    )


@pytest.fixture
def gateway(app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> Callable[[FakeGateway], FakeGateway]:
    monkeypatch.setenv("BR_DEEPSEEK_API_KEY", "sk-test-not-real")

    def install(fake: FakeGateway) -> FakeGateway:
        app.state.llm_gateway_factory = lambda spec, api_key: fake
        return fake

    return install


def login(client: TestClient) -> str:
    user_id = f"interview-api-{uuid.uuid4().hex[:8]}"
    assert client.post("/api/v1/auth/session", json={"user_id": user_id}).status_code == 200
    return user_id


def upload(client: TestClient, session_id: str, pdf: bytes | None = None, **form: str):
    data = {"count": "5"} | form
    return client.post(
        f"/api/v1/interview/sessions/{session_id}/questions",
        files={
            "file": ("cv.pdf", pdf if pdf is not None else build_resume_pdf(), "application/pdf")
        },
        data=data,
    )


def test_interview_endpoints_require_a_session(client: TestClient) -> None:
    assert client.post("/api/v1/interview/sessions", json={}).status_code == 401
    assert client.get("/api/v1/interview/sessions").status_code == 401


def test_create_and_list_sessions(client: TestClient, migrated_database: str) -> None:
    login(client)

    created = client.post("/api/v1/interview/sessions", json={"interview_type": "backend"})
    assert created.status_code == 201
    payload = created.json()
    assert payload["status"] == "draft"
    assert payload["question_count"] == 0

    listed = client.get("/api/v1/interview/sessions").json()
    assert [item["id"] for item in listed] == [payload["id"]]


def test_new_session_abandons_the_previous_one(client: TestClient, migrated_database: str) -> None:
    login(client)
    first = client.post("/api/v1/interview/sessions", json={}).json()["id"]

    second = client.post("/api/v1/interview/sessions", json={}).json()["id"]

    listed = client.get("/api/v1/interview/sessions").json()
    assert [item["id"] for item in listed] == [second]
    assert first != second


def test_generation_requires_a_configured_model(client: TestClient, migrated_database: str) -> None:
    login(client)
    session_id = client.post("/api/v1/interview/sessions", json={}).json()["id"]

    response = upload(client, session_id)

    assert response.status_code == 503
    assert "BR_DEEPSEEK_API_KEY" in response.json()["detail"]


def test_upload_and_generate_questions(client: TestClient, gateway, migrated_database: str) -> None:
    login(client)
    session_id = client.post("/api/v1/interview/sessions", json={}).json()["id"]
    fake = gateway(FakeGateway(batch(5)))

    response = upload(client, session_id)

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["replayed"] is False
    assert [q["question_no"] for q in payload["questions"]] == ["1", "2", "3", "4", "5"]
    assert payload["questions"][0]["focus_points"] == ["要点1"]
    assert payload["session"]["status"] == "ready"
    assert payload["session"]["question_count"] == 5
    assert payload["session"]["resume_score"] == 77.0
    assert payload["flow"] == {
        "status": "asking",
        "current_question_no": "1",
        "total_questions": 5,
        "follow_up_count": 0,
        "max_follow_up": 2,
    }
    assert fake.calls == 1


def test_repeat_upload_replays(client: TestClient, gateway, migrated_database: str) -> None:
    login(client)
    session_id = client.post("/api/v1/interview/sessions", json={}).json()["id"]
    fake = gateway(FakeGateway(batch(3)))

    first = upload(client, session_id, count="3")
    second = upload(client, session_id, count="3")

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["replayed"] is True
    assert [q["text"] for q in second.json()["questions"]] == [
        q["text"] for q in first.json()["questions"]
    ]
    assert fake.calls == 1


def test_unparsable_resume_returns_400_and_stays_retryable(
    client: TestClient, gateway, migrated_database: str
) -> None:
    login(client)
    session_id = client.post("/api/v1/interview/sessions", json={}).json()["id"]
    fake = gateway(FakeGateway(batch(5)))

    response = upload(client, session_id, pdf=b"definitely not a pdf")

    assert response.status_code == 400
    assert response.json()["code"] == "not_a_pdf"
    assert fake.calls == 0

    listed = client.get("/api/v1/interview/sessions").json()
    assert listed[0]["status"] == "draft"  # can retry with a good file
    assert listed[0]["question_count"] == 0


def test_vendor_timeout_maps_to_gateway_timeout(
    client: TestClient, gateway, migrated_database: str
) -> None:
    """M3 contract change: a vendor timeout leaves as 504 + kind=timeout (was 502)."""
    login(client)
    session_id = client.post("/api/v1/interview/sessions", json={}).json()["id"]
    gateway(FakeGateway(error=LlmTimeoutError("upstream slow")))

    response = upload(client, session_id)

    assert response.status_code == 504
    assert response.json()["kind"] == "timeout"

    listed = client.get("/api/v1/interview/sessions").json()
    assert listed[0]["status"] == "draft"


def test_oversized_upload_is_rejected(client: TestClient, gateway, migrated_database: str) -> None:
    from better_resume.http.interview import MAX_RESUME_BYTES

    login(client)
    session_id = client.post("/api/v1/interview/sessions", json={}).json()["id"]
    gateway(FakeGateway(batch(1)))

    response = upload(client, session_id, pdf=b"%PDF-" + b"0" * (MAX_RESUME_BYTES + 1))

    assert response.status_code == 413
