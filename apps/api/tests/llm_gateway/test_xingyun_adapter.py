"""M5-T3/T4: the Xingyun adapter against a local fake workflow server (real HTTP + SSE)."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest
from pydantic import BaseModel

from better_resume.llm_gateway import LlmScene
from better_resume.llm_gateway.adapters.xingyun import XingyunWorkflowAdapter
from better_resume.llm_gateway.binding_store import SceneBinding
from better_resume.llm_gateway.errors import LlmSchemaError, LlmVendorError
from better_resume.llm_gateway.models import (
    ChatRequest,
    ContentDelta,
    Done,
    Message,
    ReasoningDelta,
)
from better_resume.llm_gateway.scene_mapping import to_xingyun_payload, validate_structured
from better_resume.llm_gateway.scenes import AdapterKind
from better_resume.llm_gateway.xingyun_factory import (
    API_KEY_ENV,
    API_SECRET_ENV,
    XingyunGatewayFactory,
)


class Score(BaseModel):
    score: float
    feedback: str


class FakeWorkflow(BaseHTTPRequestHandler):
    """Speaks just enough HTTP/1.1 + SSE to be a real server for the adapter."""

    frames: list[dict[str, Any]] = []
    status = 200
    requests: list[dict[str, Any]] = []

    def do_POST(self) -> None:  # noqa: N802 - http.server API
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length) or b"{}")
        type(self).requests.append({"headers": dict(self.headers), "body": body})

        if type(self).status >= 400:
            payload = json.dumps({"error": "boom"}).encode()
            self.send_response(type(self).status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for frame in type(self).frames:
            self.wfile.write(f"data:{json.dumps(frame)}\n\n".encode())
            self.wfile.flush()
        self.wfile.write(b"data:[DONE]\n\n")
        self.wfile.flush()

    def log_message(self, *args: object) -> None:  # keep pytest output clean
        return


@pytest.fixture
def server():
    FakeWorkflow.frames = []
    FakeWorkflow.requests = []
    FakeWorkflow.status = 200
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), FakeWorkflow)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}/workflow/v1/chat/completions"
    httpd.shutdown()
    httpd.server_close()


def adapter(server: str, *, scene: LlmScene = LlmScene.ANSWER_EVALUATION, **kwargs: Any):
    return XingyunWorkflowAdapter(
        scene=scene,
        flow_id="flow-123",
        api_key="key-1",
        api_secret="secret-1",
        base_url=server,
        max_attempts=1,
        sleep=_no_sleep,
        **kwargs,
    )


async def _no_sleep(_seconds: float) -> None:
    return None


def request(schema: type[BaseModel] | None = None) -> ChatRequest:
    return ChatRequest(
        messages=[
            Message(role="system", content="你是评分官"),
            Message(role="user", content="这是我的答案"),
        ],
        response_schema=schema,
    )


async def test_payload_is_the_documented_shape_and_bearer_auth(server: str) -> None:
    FakeWorkflow.frames = [{"event": "message", "content": '{"score": 80, "feedback": "ok"}'}]

    await adapter(server).complete(request(Score))

    sent = FakeWorkflow.requests[0]
    assert sent["headers"]["Authorization"] == "Bearer key-1:secret-1"
    body = sent["body"]
    assert body["flow_id"] == "flow-123"
    assert body["stream"] is True
    assert body["uid"] == "better-resume"
    assert body["parameters"]["scene"] == "answer_evaluation"
    assert body["parameters"]["user_input"] == "这是我的答案"
    assert body["parameters"]["expect_fields"] == ["feedback", "score"]
    assert body["history"][0]["role"] == "system"


async def test_stream_is_normalised(server: str) -> None:
    FakeWorkflow.frames = [
        {"event": "message", "content": "你"},
        {"event": "message", "reasoning_content": "先想"},
        {"event": "message", "content": "好"},
    ]

    events = [event async for event in adapter(server).stream(request())]

    assert [e.text for e in events if isinstance(e, ContentDelta)] == ["你", "好"]
    assert [e.text for e in events if isinstance(e, ReasoningDelta)] == ["先想"]
    assert isinstance(events[-1], Done)


async def test_complete_validates_the_schema(server: str) -> None:
    FakeWorkflow.frames = [{"event": "message", "content": '{"score": 91, "feedback": "很好"}'}]

    result = await adapter(server).complete(request(Score))

    assert isinstance(result.parsed, Score)
    assert result.parsed.score == 91
    assert result.model == "xingyun:flow-123"


async def test_schema_failure_retries_once_then_raises(server: str) -> None:
    FakeWorkflow.frames = [{"event": "message", "content": "not json at all"}]

    with pytest.raises(LlmSchemaError, match="not valid JSON"):
        await adapter(server, schema_retries=1).complete(request(Score))

    assert len(FakeWorkflow.requests) == 2  # asked twice, then gave up


async def test_alias_fields_are_not_accepted(server: str) -> None:
    FakeWorkflow.frames = [{"event": "message", "content": '{"total_score": 77, "comment": "x"}'}]

    with pytest.raises(LlmSchemaError, match="does not match Score"):
        await adapter(server, schema_retries=0).complete(request(Score))


async def test_unknown_events_and_frames_are_ignored(server: str) -> None:
    FakeWorkflow.frames = [
        {"event": "progress", "content": "ignored"},
        {"event": "message"},
        {"event": "message", "content": "保留"},
    ]

    events = [event async for event in adapter(server).stream(request())]
    texts = [event.text for event in events if isinstance(event, ContentDelta)]

    assert texts == ["保留"]


async def test_done_event_finishes_the_stream(server: str) -> None:
    FakeWorkflow.frames = [{"event": "message", "content": "半句"}, {"event": "done"}]

    events = [event async for event in adapter(server).stream(request())]

    assert events[-1] == Done(finish_reason="stop")


async def test_vendor_errors_are_classified(server: str) -> None:
    FakeWorkflow.status = 401
    with pytest.raises(LlmVendorError) as unauthorized:
        await adapter(server).complete(request())
    assert unauthorized.value.retryable is False
    assert "401" in str(unauthorized.value)


async def test_factory_reports_missing_credentials() -> None:
    empty = XingyunGatewayFactory(environ={})
    binding = SceneBinding(
        scene=LlmScene.FOLLOW_UP, adapter=AdapterKind.XINGYUN, target_ref="flow-1"
    )

    assert empty.is_configured(binding) is False
    with pytest.raises(Exception, match="missing"):
        await empty.build(binding)

    configured = XingyunGatewayFactory(
        environ={API_KEY_ENV: "k", API_SECRET_ENV: "s"}, base_url="http://localhost:1"
    )
    assert configured.is_configured(binding) is True
    gateway = await configured.build(binding)
    assert isinstance(gateway, XingyunWorkflowAdapter)
    await gateway.aclose()


def test_mapping_is_explicit_per_scene() -> None:
    payload = to_xingyun_payload(
        LlmScene.CHAT,
        ChatRequest(messages=[Message(role="user", content="你好")]),
        flow_id="f",
        uid="u",
    )

    assert payload["parameters"]["scene"] == "chat"
    assert "expect_fields" not in payload["parameters"]  # chat has no schema


def test_validate_structured_is_strict() -> None:
    assert validate_structured(Score, '{"score": 1, "feedback": "x"}').score == 1
    with pytest.raises(LlmSchemaError):
        validate_structured(Score, '{"score": 1}')
    with pytest.raises(LlmSchemaError):
        validate_structured(Score, "[]")
