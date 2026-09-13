"""T3: chat HTTP surface — session lifecycle, history paging and the SSE stream."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator, Callable

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from better_resume.llm_gateway import (
    ChatRequest,
    ChatResult,
    ContentDelta,
    Done,
    LlmTimeoutError,
    ReasoningDelta,
    StreamEvent,
    VendorMeta,
)
from better_resume.main import create_app
from better_resume.settings import Settings


class FakeGateway:
    def __init__(
        self, events: list[StreamEvent], *, error: Exception | None = None, delay: float = 0.0
    ):
        self._events = events
        self._error = error
        self._delay = delay

    def stream(self, req: ChatRequest) -> AsyncIterator[StreamEvent]:
        return self._stream(req)

    async def _stream(self, req: ChatRequest) -> AsyncIterator[StreamEvent]:
        for event in self._events:
            if self._delay:
                await asyncio.sleep(self._delay)
            yield event
        if self._error is not None:
            raise self._error

    async def complete(self, req: ChatRequest) -> ChatResult:  # pragma: no cover - unused
        raise NotImplementedError


@pytest.fixture
def fake_gateway(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> Callable[[FakeGateway], FakeGateway]:
    """Swap the vendor boundary: needs a configured key, because the endpoint checks it first."""
    monkeypatch.setenv("BR_DEEPSEEK_API_KEY", "sk-test-not-real")

    def install(gateway: FakeGateway) -> FakeGateway:
        app.state.llm_gateway_factory = lambda spec, api_key: gateway
        return gateway

    return install


def login(client: TestClient) -> str:
    """Each test gets its own user so DB state never leaks between cases."""
    user_id = f"chat-api-{uuid.uuid4().hex[:8]}"
    assert client.post("/api/v1/auth/session", json={"user_id": user_id}).status_code == 200
    return user_id


def create_session(client: TestClient, title: str = "会话") -> str:
    response = client.post("/api/v1/chat/sessions", json={"title": title})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def parse_sse(text: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block or block.startswith(":"):
            continue
        name = ""
        data = ""
        for line in block.splitlines():
            if line.startswith("event:"):
                name = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data = line[len("data:") :].strip()
        if name:
            events.append((name, json.loads(data) if data else {}))
    return events


def test_chat_endpoints_require_a_session(client: TestClient) -> None:
    assert client.get("/api/v1/chat/sessions").status_code == 401
    assert client.post("/api/v1/chat/sessions", json={}).status_code == 401


def test_session_lifecycle(client: TestClient, migrated_database: str) -> None:
    login(client)
    session_id = create_session(client, "第一个会话")

    listed = client.get("/api/v1/chat/sessions").json()
    assert [item["id"] for item in listed] == [session_id]
    assert listed[0]["title"] == "第一个会话"
    assert listed[0]["message_count"] == 0

    assert client.get(f"/api/v1/chat/sessions/{session_id}/messages").json() == []

    renamed = client.put(f"/api/v1/chat/sessions/{session_id}", json={"title": "改过的标题"})
    assert renamed.status_code == 204
    assert client.get("/api/v1/chat/sessions").json()[0]["title"] == "改过的标题"

    assert client.delete(f"/api/v1/chat/sessions/{session_id}").status_code == 204
    assert client.get("/api/v1/chat/sessions").json() == []
    assert client.get(f"/api/v1/chat/sessions/{session_id}/messages").status_code == 404


def test_stream_without_configured_key_fails_honestly(
    client: TestClient, migrated_database: str
) -> None:
    login(client)
    session_id = create_session(client)

    response = client.post(f"/api/v1/chat/sessions/{session_id}/stream", json={"content": "你好"})

    assert response.status_code == 503
    assert "BR_DEEPSEEK_API_KEY" in response.json()["detail"]


def test_stream_emits_normalized_sse_frames(
    client: TestClient, fake_gateway, migrated_database: str
) -> None:
    login(client)
    session_id = create_session(client)
    fake_gateway(
        FakeGateway(
            [
                ReasoningDelta(text="先想"),
                ContentDelta(text="你"),
                ContentDelta(text="好"),
                VendorMeta(model="deepseek-flash", extra={"usage": {"total_tokens": 9}}),
                Done(finish_reason="stop"),
            ]
        )
    )

    with client.stream(
        "POST",
        f"/api/v1/chat/sessions/{session_id}/stream",
        json={"content": "你好", "client_message_id": "cm-1"},
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert response.headers["cache-control"] == "no-cache"
        text = "".join(response.iter_text())

    events = parse_sse(text)
    assert [name for name, _ in events] == ["reasoning", "content", "content", "meta", "done"]
    assert "".join(payload["text"] for name, payload in events if name == "content") == "你好"
    assert events[-1][1]["finish_reason"] == "stop"

    messages = client.get(f"/api/v1/chat/sessions/{session_id}/messages").json()
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[1]["content"] == "你好"
    assert messages[1]["reasoning"] == "先想"
    assert messages[1]["token_count"] == 9


def test_stream_error_frame_is_persisted(
    client: TestClient, fake_gateway, migrated_database: str
) -> None:
    login(client)
    session_id = create_session(client)
    fake_gateway(
        FakeGateway([ContentDelta(text="半句")], error=LlmTimeoutError("upstream timeout"))
    )

    with client.stream(
        "POST", f"/api/v1/chat/sessions/{session_id}/stream", json={"content": "会失败的请求"}
    ) as response:
        text = "".join(response.iter_text())

    events = parse_sse(text)
    assert [name for name, _ in events] == ["content", "error"]
    # M3: the resilience seam normalises vendor failures, so the frame carries the
    # taxonomy kind (timeout/overloaded/unavailable/invalid) instead of "retryable".
    assert events[-1][1]["kind"] == "timeout"

    messages = client.get(f"/api/v1/chat/sessions/{session_id}/messages").json()
    assert messages[1]["content"] == "半句"
    assert messages[1]["error_message"]


def test_duplicate_client_message_id_is_reported(
    client: TestClient, fake_gateway, migrated_database: str
) -> None:
    login(client)
    session_id = create_session(client)
    fake_gateway(FakeGateway([ContentDelta(text="第一次")]))
    body = {"content": "你好", "client_message_id": "cm-dup"}

    with client.stream("POST", f"/api/v1/chat/sessions/{session_id}/stream", json=body) as first:
        first.read()
    with client.stream("POST", f"/api/v1/chat/sessions/{session_id}/stream", json=body) as second:
        text = "".join(second.iter_text())

    events = parse_sse(text)
    assert [name for name, _ in events] == ["error"]
    assert events[0][1]["kind"] == "duplicate_request"
    assert len(client.get(f"/api/v1/chat/sessions/{session_id}/messages").json()) == 2


def test_heartbeat_frames_keep_slow_streams_alive(migrated_database: str, monkeypatch) -> None:
    monkeypatch.setenv("BR_DEEPSEEK_API_KEY", "sk-test-not-real")
    settings = Settings(
        _env_file=None,
        environment="test",
        log_level="WARNING",
        sse_heartbeat_seconds=0.05,
        database_url=migrated_database,
    )
    app = create_app(settings)

    with TestClient(app) as client:
        # lifespan installs the real factory, so the fake must go in afterwards.
        app.state.llm_gateway_factory = lambda spec, api_key: FakeGateway(
            [ContentDelta(text="慢"), Done(finish_reason="stop")], delay=0.3
        )
        login(client)
        session_id = create_session(client)
        with client.stream(
            "POST", f"/api/v1/chat/sessions/{session_id}/stream", json={"content": "慢问题"}
        ) as response:
            text = "".join(response.iter_text())

    assert ": ping" in text
    assert parse_sse(text)[-1][0] == "done"


def test_history_paging_uses_seq_cursor(
    client: TestClient, fake_gateway, migrated_database: str
) -> None:
    login(client)
    session_id = create_session(client)
    fake_gateway(FakeGateway([ContentDelta(text="答")]))

    for index in range(3):
        with client.stream(
            "POST",
            f"/api/v1/chat/sessions/{session_id}/stream",
            json={"content": f"问{index}"},
        ) as response:
            response.read()

    latest = client.get(f"/api/v1/chat/sessions/{session_id}/messages", params={"limit": 2}).json()
    assert [m["content"] for m in latest] == ["问2", "答"]  # ascending seq order

    earlier = client.get(
        f"/api/v1/chat/sessions/{session_id}/messages",
        params={"before": latest[0]["seq"], "limit": 2},
    ).json()
    assert [m["content"] for m in earlier] == ["问1", "答"]
