"""P3: DashScope application-call adapter against a local fake app server (real HTTP + SSE).

Protocol (verified against the Model Studio "call applications" doc, 2026-09-17):
`POST {base}/api/v1/apps/{app_id}/completion` with `Authorization: Bearer <key>`, and
`X-DashScope-SSE: enable` for streaming. Frames are the batch envelope:
`{"output":{"text","finish_reason","session_id"},"usage":{"models":[...]},"request_id"}`.

The cloud application owns the prompt; we own the input mapping and the output contract.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest
from pydantic import BaseModel

from better_resume.llm_gateway import LlmScene
from better_resume.llm_gateway.adapters.dashscope_app import DashScopeAppAdapter
from better_resume.llm_gateway.errors import LlmSchemaError, LlmVendorError
from better_resume.llm_gateway.models import (
    ChatRequest,
    ContentDelta,
    Done,
    Message,
    ReasoningDelta,
    VendorContext,
)
from better_resume.llm_gateway.scene_mapping import to_dashscope_app_payload


class Score(BaseModel):
    score: float
    feedback: str


class FakeApp(BaseHTTPRequestHandler):
    """Speaks the vendor's SSE plumbing (id / event / :HTTP_STATUS comment / data)."""

    frames: list[dict[str, Any]] = []
    status = 200
    #: the real vendor reports in-band failures as an SSE frame preceded by this comment
    frame_status = 200
    requests: list[dict[str, Any]] = []

    def do_POST(self) -> None:  # noqa: N802 - http.server API
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length) or b"{}")
        type(self).requests.append({"path": self.path, "headers": dict(self.headers), "body": body})

        if type(self).status >= 400:
            payload = json.dumps({"code": "InvalidApiKey", "message": "boom"}).encode()
            self.send_response(type(self).status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for index, frame in enumerate(type(self).frames, start=1):
            event = "error" if "code" in frame else "result"
            chunk = (
                f"id:{index}\nevent:{event}\n:HTTP_STATUS/{type(self).frame_status}\n"
                f"data:{json.dumps(frame)}\n\n"
            )
            self.wfile.write(chunk.encode())
            self.wfile.flush()

    def log_message(self, *args: object) -> None:  # keep pytest output clean
        return


@pytest.fixture
def server():
    FakeApp.frames = []
    FakeApp.requests = []
    FakeApp.status = 200
    FakeApp.frame_status = 200
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), FakeApp)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


async def _no_sleep(_seconds: float) -> None:
    return None


def adapter(server: str, *, scene: LlmScene = LlmScene.ANSWER_EVALUATION, **kwargs: Any):
    kwargs.setdefault("max_attempts", 1)
    return DashScopeAppAdapter(
        scene=scene,
        app_id="app-123",
        api_key="sk-test",
        base_url=server,
        sleep=_no_sleep,
        **kwargs,
    )


def request(schema: type[BaseModel] | None = None) -> ChatRequest:
    return ChatRequest(
        messages=[
            Message(role="system", content="你是评分官"),
            Message(role="user", content="这是我的答案"),
        ],
        response_schema=schema,
    )


async def test_request_targets_the_app_endpoint_with_bearer_and_sse(server: str) -> None:
    FakeApp.frames = [{"output": {"text": "好", "finish_reason": "stop"}}]

    await adapter(server).complete(request())

    sent = FakeApp.requests[0]
    assert sent["path"] == "/api/v1/apps/app-123/completion"
    assert sent["headers"]["Authorization"] == "Bearer sk-test"
    assert sent["headers"]["X-DashScope-SSE"] == "enable"
    assert sent["body"]["input"]["prompt"] == "这是我的答案"
    assert sent["body"]["parameters"]["incremental_output"] is True
    # The cloud app owns its prompt: we do not ship our own system prompt or schema hints.
    assert "expect_fields" not in json.dumps(sent["body"])


async def test_stream_is_normalised_and_ignores_sse_plumbing(server: str) -> None:
    FakeApp.frames = [
        {"output": {"text": "你", "finish_reason": "null"}},
        {"output": {"text": "好", "finish_reason": "null"}},
        {"output": {"text": "", "finish_reason": "stop"}},
    ]

    events = [event async for event in adapter(server).stream(request())]

    assert [event.text for event in events if isinstance(event, ContentDelta)] == ["你", "好"]
    assert events[-1] == Done(finish_reason="stop")


async def test_thoughts_become_reasoning_deltas(server: str) -> None:
    FakeApp.frames = [
        {"output": {"thoughts": "先想", "text": "", "finish_reason": "null"}},
        {"output": {"text": "答案", "finish_reason": "stop"}},
    ]

    events = [event async for event in adapter(server).stream(request())]

    assert [event.text for event in events if isinstance(event, ReasoningDelta)] == ["先想"]
    assert [event.text for event in events if isinstance(event, ContentDelta)] == ["答案"]


async def test_in_band_error_frames_are_not_empty_successes(server: str) -> None:
    """The vendor answers HTTP 200 with an `event:error` frame (seen on the real endpoint,
    2026-09-17). Treating that as an empty answer hides a broken binding behind a blank reply."""
    FakeApp.frame_status = 400
    FakeApp.frames = [
        {
            "code": "InvalidParameter",
            "message": (
                "Required parameter(AppId) missing or invalid, please check the request parameters."
            ),
            "request_id": "req-1",
        }
    ]

    with pytest.raises(LlmVendorError) as caught:
        await adapter(server).complete(request())

    assert "InvalidParameter" in str(caught.value)
    assert "AppId" in str(caught.value)
    assert caught.value.retryable is False
    assert caught.value.status_code == 400


async def test_in_band_server_errors_stay_retryable(server: str) -> None:
    FakeApp.frame_status = 500
    FakeApp.frames = [{"code": "InternalError", "message": "upstream exploded"}]

    with pytest.raises(LlmVendorError) as caught:
        await adapter(server, max_attempts=1).complete(request())

    assert caught.value.retryable is True


async def test_an_error_after_partial_text_still_fails(server: str) -> None:
    FakeApp.frame_status = 400
    FakeApp.frames = [
        {"output": {"text": "半句", "finish_reason": "null"}},
        {"code": "InvalidParameter", "message": "boom"},
    ]

    with pytest.raises(LlmVendorError):
        await adapter(server).complete(request())


async def test_usage_is_mapped_from_the_vendor_envelope(server: str) -> None:
    FakeApp.frames = [
        {
            "output": {"text": "你好", "finish_reason": "stop"},
            "usage": {
                "models": [{"input_tokens": 203, "output_tokens": 8, "model_id": "qwen-max"}]
            },
            "request_id": "req-1",
        }
    ]

    result = await adapter(server).complete(request())

    assert result.usage is not None
    assert result.usage.prompt_tokens == 203
    assert result.usage.completion_tokens == 8
    assert result.usage.total_tokens == 211
    assert result.model == "dashscope-app:app-123"


async def test_complete_validates_the_schema(server: str) -> None:
    FakeApp.frames = [
        {"output": {"text": '{"score": 91, "feedback": "很好"}', "finish_reason": "stop"}}
    ]

    result = await adapter(server).complete(request(Score))

    assert isinstance(result.parsed, Score)
    assert result.parsed.score == 91


async def test_schema_failure_retries_once_then_raises(server: str) -> None:
    FakeApp.frames = [{"output": {"text": "not json at all", "finish_reason": "stop"}}]

    with pytest.raises(LlmSchemaError, match="not valid JSON"):
        await adapter(server, schema_retries=1).complete(request(Score))

    assert len(FakeApp.requests) == 2  # asked twice, then gave up


async def test_alias_fields_are_not_accepted(server: str) -> None:
    FakeApp.frames = [
        {"output": {"text": '{"total_score": 77, "comment": "x"}', "finish_reason": "stop"}}
    ]

    with pytest.raises(LlmSchemaError, match="does not match Score"):
        await adapter(server, schema_retries=0).complete(request(Score))


async def test_vendor_errors_are_classified(server: str) -> None:
    FakeApp.status = 401
    with pytest.raises(LlmVendorError) as unauthorized:
        await adapter(server).complete(request())
    assert unauthorized.value.retryable is False
    assert "401" in str(unauthorized.value)


async def test_retryable_vendor_errors_are_retried(server: str) -> None:
    FakeApp.status = 500
    with pytest.raises(LlmVendorError) as upstream:
        await adapter(server, max_attempts=2).complete(request())
    assert upstream.value.retryable is True
    assert len(FakeApp.requests) == 2


async def test_session_id_comes_from_the_vendor_context(server: str) -> None:
    FakeApp.frames = [{"output": {"text": "好", "finish_reason": "stop"}}]
    req = ChatRequest(
        messages=[Message(role="user", content="接着说")],
        vendor_ctx=VendorContext(vendor="dashscope_app", workflow_id="session-9"),
    )

    await adapter(server).complete(req)

    assert FakeApp.requests[0]["body"]["input"]["session_id"] == "session-9"


def test_adapter_refuses_to_be_built_without_app_id_or_key() -> None:
    with pytest.raises(LlmSchemaError, match="app_id"):
        DashScopeAppAdapter(scene=LlmScene.CHAT, app_id="", api_key="sk-test")


def test_payload_never_sends_our_system_prompt() -> None:
    payload = to_dashscope_app_payload(
        ChatRequest(
            messages=[
                Message(role="system", content="你是评分官"),
                Message(role="user", content="用户问题"),
            ]
        ),
        app_id="app-1",
    )

    assert payload == {
        "input": {"prompt": "用户问题"},
        "parameters": {"incremental_output": True},
        "debug": {},
    }
