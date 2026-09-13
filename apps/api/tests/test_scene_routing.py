"""M5-T6: every AI endpoint resolves its own scene — switching providers edits no business code."""

from __future__ import annotations

import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from better_resume.llm_gateway import AdapterKind, LlmScene, SceneBinding
from better_resume.llm_gateway.protocols import LlmGateway
from better_resume.main import create_app
from better_resume.settings import Settings

from .interview_engine.test_parser_helpers import build_resume_pdf
from .test_interview_answers_api import FakeGateway as SchemaAnsweringGateway
from .test_interview_api import FakeGateway, batch


class RecordingFactory:
    """A second provider that records which binding it was asked to serve."""

    def __init__(self, gateway: LlmGateway, *, configured: bool = True) -> None:
        self.gateway = gateway
        self.configured = configured
        self.bindings: list[SceneBinding] = []

    def is_configured(self, binding: SceneBinding) -> bool:
        return self.configured

    async def build(self, binding: SceneBinding) -> LlmGateway:
        self.bindings.append(binding)
        return self.gateway


def login(client: TestClient) -> str:
    user_id = f"routing-{uuid.uuid4().hex[:8]}"
    assert client.post("/api/v1/auth/session", json={"user_id": user_id}).status_code == 200
    return user_id


def new_session(client: TestClient) -> str:
    response = client.post("/api/v1/interview/sessions", json={})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def upload(client: TestClient, session_id: str):
    return client.post(
        f"/api/v1/interview/sessions/{session_id}/questions",
        files={"file": ("cv.pdf", build_resume_pdf(), "application/pdf")},
        data={"count": "3"},
    )


def install_factory(app: FastAPI, factory: RecordingFactory) -> RecordingFactory:
    app.state.scene_resolver.register_factory(AdapterKind.XINGYUN, factory)
    return factory


def switch(client: TestClient, scene: str, adapter: str, target: str) -> None:
    response = client.put(
        f"/api/v1/scenes/{scene}", json={"adapter": adapter, "target_ref": target}
    )
    assert response.status_code == 200, response.text


def test_question_extraction_follows_its_binding(
    client: TestClient, app: FastAPI, migrated_database: str
) -> None:
    login(client)
    session_id = new_session(client)
    fake = FakeGateway(batch(3))
    factory = install_factory(app, RecordingFactory(fake))

    switch(client, LlmScene.QUESTION_EXTRACTION.value, "xingyun", "flow-questions")
    response = upload(client, session_id)

    assert response.status_code == 201, response.text
    assert [binding.target_ref for binding in factory.bindings] == ["flow-questions"]
    assert fake.calls == 1
    # restore the default for the rest of the suite
    switch(client, LlmScene.QUESTION_EXTRACTION.value, "openai_compat", "deepseek-flash")


def test_scoring_follows_the_evaluation_binding(
    client: TestClient, app: FastAPI, migrated_database: str
) -> None:
    login(client)
    session_id = new_session(client)
    prepared = FakeGateway(batch(3))
    install_factory(app, RecordingFactory(prepared))
    switch(client, LlmScene.QUESTION_EXTRACTION.value, "xingyun", "flow-questions")
    assert upload(client, session_id).status_code == 201

    scorer = SchemaAnsweringGateway(score=88.0)  # answers whichever schema is asked
    factory = install_factory(app, RecordingFactory(scorer))
    switch(client, LlmScene.ANSWER_EVALUATION.value, "xingyun", "flow-scores")
    switch(client, LlmScene.FOLLOW_UP.value, "xingyun", "flow-follow-up")

    response = client.post(
        f"/api/v1/interview/sessions/{session_id}/answers",
        json={"question_no": "1", "answer": "我负责了订单链路重构", "request_id": "r-1"},
    )

    assert response.status_code == 201, response.text
    targets = [binding.target_ref for binding in factory.bindings]
    assert "flow-scores" in targets
    assert "flow-follow-up" in targets

    switch(client, LlmScene.QUESTION_EXTRACTION.value, "openai_compat", "deepseek-flash")
    switch(client, LlmScene.ANSWER_EVALUATION.value, "openai_compat", "deepseek-flash")
    switch(client, LlmScene.FOLLOW_UP.value, "openai_compat", "deepseek-flash")


def test_report_summary_follows_its_binding(
    client: TestClient, app: FastAPI, migrated_database: str
) -> None:
    login(client)
    session_id = new_session(client)
    install_factory(app, RecordingFactory(FakeGateway(batch(3))))

    factory = install_factory(app, RecordingFactory(FakeGateway(batch(1))))
    switch(client, LlmScene.REPORT_SUMMARY.value, "xingyun", "flow-summary")

    # A draft session cannot be finished (409), but the endpoint resolves its scene first:
    # that is exactly the routing we are pinning down here.
    response = client.post(f"/api/v1/interview/sessions/{session_id}/finish")

    assert response.status_code == 409, response.text
    assert [binding.target_ref for binding in factory.bindings] == ["flow-summary"]
    switch(client, LlmScene.REPORT_SUMMARY.value, "openai_compat", "deepseek-flash")


def test_unconfigured_scene_is_a_503_not_a_crash(
    client: TestClient, app: FastAPI, migrated_database: str
) -> None:
    login(client)
    install_factory(app, RecordingFactory(FakeGateway(batch(3)), configured=False))
    switch(client, LlmScene.CHAT.value, "xingyun", "flow-chat")

    response = client.post("/api/v1/chat/sessions", json={"title": "t"})
    assert response.status_code == 201
    session_id = response.json()["id"]
    streamed = client.post(f"/api/v1/chat/sessions/{session_id}/stream", json={"content": "你好"})

    assert streamed.status_code == 503
    assert "not configured" in streamed.json()["detail"]
    switch(client, LlmScene.CHAT.value, "openai_compat", "deepseek-flash")


def test_explicit_model_ref_still_overrides_the_binding(
    app: FastAPI, migrated_database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BR_DEEPSEEK_API_KEY", "sk-test-not-real")
    settings = Settings(
        _env_file=None, database_url=app.state.settings.database_url, environment="test"
    )
    custom = create_app(settings)
    xingyun_gateway = FakeGateway(batch(3))
    factory = RecordingFactory(xingyun_gateway)
    with TestClient(custom) as client:
        custom.state.scene_resolver.register_factory(AdapterKind.XINGYUN, factory)
        openai_calls: list[str] = []

        def fake_builder(spec: object, api_key: str) -> LlmGateway:
            def gateway() -> LlmGateway:
                raise AssertionError("unused")

            openai_calls.append(getattr(spec, "name", "?"))
            return FakeGateway(batch(3))  # type: ignore[return-value]

        custom.state.llm_gateway_factory = fake_builder  # type: ignore[assignment]
        login(client)
        session_id = client.post("/api/v1/chat/sessions", json={"title": "t"}).json()["id"]
        switch(client, LlmScene.CHAT.value, "xingyun", "flow-chat")

        response = client.post(
            f"/api/v1/chat/sessions/{session_id}/stream",
            json={"content": "你好", "model_ref": "deepseek-flash"},
        )

        assert response.status_code == 200
        assert openai_calls, "the explicit model_ref must win over the scene binding"
        assert factory.bindings == []
