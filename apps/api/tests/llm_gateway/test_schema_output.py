"""T2: structured output is validated against the caller's Pydantic schema."""

from __future__ import annotations

import json

import httpx
import pytest
from pydantic import BaseModel

from better_resume.llm_gateway import ChatRequest, LlmSchemaError, Message
from better_resume.llm_gateway.adapters.openai_compat import OpenAICompatAdapter
from better_resume.llm_gateway.models import ModelSpec

SPEC = ModelSpec(
    name="deepseek-flash",
    provider="deepseek",
    base_url="https://api.deepseek.com",
    model_id="deepseek-flash",
    api_key_env="BR_DEEPSEEK_API_KEY",
)


class Score(BaseModel):
    value: float


def completion(content: str) -> bytes:
    payload = {
        "id": "x",
        "object": "chat.completion",
        "model": "deepseek-flash",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
    }
    return json.dumps(payload).encode()


def build(
    contents: list[str], *, seen: list[dict] | None = None
) -> tuple[OpenAICompatAdapter, dict]:
    state = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(json.loads(request.content))
        index = min(state["n"], len(contents) - 1)
        state["n"] += 1
        return httpx.Response(200, content=completion(contents[index]))

    async def no_sleep(seconds: float) -> None:
        return None

    return OpenAICompatAdapter(
        SPEC,
        api_key="k",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        sleep=no_sleep,
    ), state


async def test_valid_json_is_parsed_into_the_schema() -> None:
    adapter, _ = build(['{"value": 0.5}'])

    result = await adapter.complete(
        ChatRequest(messages=[Message(role="user", content="score")], response_schema=Score)
    )

    assert result.parsed is not None
    assert result.parsed.value == 0.5


async def test_invalid_json_is_retried_then_succeeds() -> None:
    adapter, state = build(['{"value": "nope"}', '{"value": 0.7}'])

    result = await adapter.complete(
        ChatRequest(messages=[Message(role="user", content="score")], response_schema=Score)
    )

    assert state["n"] == 2
    assert result.parsed is not None
    assert result.parsed.value == 0.7


async def test_persistently_invalid_json_raises_schema_error() -> None:
    adapter, state = build(["not json at all"])

    with pytest.raises(LlmSchemaError):
        await adapter.complete(
            ChatRequest(messages=[Message(role="user", content="score")], response_schema=Score)
        )

    assert state["n"] == 2  # one attempt + one retry


async def test_schema_request_asks_vendor_for_json_object() -> None:
    seen: list[dict] = []
    adapter, _ = build(['{"value": 0.1}'], seen=seen)

    await adapter.complete(
        ChatRequest(messages=[Message(role="user", content="score")], response_schema=Score)
    )

    assert seen[0]["response_format"] == {"type": "json_object"}
    assert "stream" not in seen[0] or seen[0]["stream"] is False


async def test_plain_completion_does_not_send_response_format() -> None:
    seen: list[dict] = []
    adapter, _ = build(["hello"], seen=seen)

    result = await adapter.complete(ChatRequest(messages=[Message(role="user", content="hi")]))

    assert "response_format" not in seen[0]
    assert result.parsed is None
    assert result.content == "hello"
