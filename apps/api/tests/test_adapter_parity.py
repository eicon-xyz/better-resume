"""M5-T8: the two providers must agree on the contract for the same scene input."""

from __future__ import annotations

import json

import httpx
import pytest
from pydantic import BaseModel

from better_resume.llm_gateway import LlmScene
from better_resume.llm_gateway.adapters.openai_compat import OpenAICompatAdapter
from better_resume.llm_gateway.adapters.xingyun import XingyunWorkflowAdapter
from better_resume.llm_gateway.errors import LlmError, LlmTimeoutError
from better_resume.llm_gateway.models import ChatRequest, Message, ModelSpec

ANSWER = {
    "score": 77,
    "feedback": "覆盖了主干",
    "missing_points": ["并发量级"],
    "follow_up_needed": True,
}


class Score(BaseModel):
    score: float
    feedback: str
    missing_points: list[str] = []
    follow_up_needed: bool = False


SPEC = ModelSpec(
    name="deepseek-flash",
    provider="deepseek",
    base_url="https://api.deepseek.com",
    model_id="deepseek-flash",
    api_key_env="BR_TEST_KEY",
)


async def _no_sleep(_seconds: float) -> None:
    return None


def request() -> ChatRequest:
    return ChatRequest(messages=[Message(role="user", content="请评分")], response_schema=Score)


def adapters(handler: object) -> tuple[OpenAICompatAdapter, XingyunWorkflowAdapter]:
    transport = httpx.MockTransport(handler)  # type: ignore[arg-type]
    openai = OpenAICompatAdapter(
        SPEC,
        api_key="k",
        client=httpx.AsyncClient(transport=transport),
        sleep=_no_sleep,
    )
    xingyun = XingyunWorkflowAdapter(
        scene=LlmScene.ANSWER_EVALUATION,
        flow_id="flow-parity",
        api_key="k",
        api_secret="s",
        client=httpx.AsyncClient(transport=transport),
        sleep=_no_sleep,
    )
    return openai, xingyun


async def test_both_providers_parse_the_same_fields() -> None:
    payloads: list[dict] = []

    def handler(request_: httpx.Request) -> httpx.Response:
        payloads.append(json.loads(request_.content or b"{}"))
        if "flow_id" in payloads[-1]:  # the Xingyun adapter always streams
            frame = {"event": "message", "content": json.dumps(ANSWER)}
            return httpx.Response(200, text=f"data:{json.dumps(frame)}\n\ndata:[DONE]\n\n")
        if payloads[-1].get("stream"):
            # OpenAI streaming shape
            frame = {"choices": [{"delta": {"content": json.dumps(ANSWER)}}]}
            return httpx.Response(200, text=f"data: {json.dumps(frame)}\n\ndata: [DONE]\n\n")
        return httpx.Response(
            200,
            json={
                "model": "deepseek-flash",
                "choices": [{"message": {"content": json.dumps(ANSWER)}}],
            },
        )

    openai, xingyun = adapters(handler)

    from_openai = await openai.complete(request())
    from_xingyun = await xingyun.complete(request())

    assert isinstance(from_openai.parsed, Score)
    assert isinstance(from_xingyun.parsed, Score)
    assert sorted(from_openai.parsed.model_dump()) == sorted(from_xingyun.parsed.model_dump())
    assert from_openai.parsed.score == from_xingyun.parsed.score == 77


async def test_both_providers_classify_failures_the_same_way() -> None:
    def timeout_handler(request_: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("boom", request=request_)

    for gateway in adapters(timeout_handler):
        with pytest.raises(LlmTimeoutError):
            await gateway.complete(request())

    def unauthorized_handler(request_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="nope")

    for gateway in adapters(unauthorized_handler):
        with pytest.raises(LlmError) as caught:
            await gateway.complete(request())
        assert caught.value.retryable is False
