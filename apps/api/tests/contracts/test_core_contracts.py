"""Contract smoke tests for conversation / llm-gateway / ai-resilience (§12.2 signatures)."""

from __future__ import annotations

import importlib
import inspect

import httpx
import pytest
from pydantic import BaseModel

from better_resume.ai_resilience import (
    AiResilience,
    Stage,
    UnimplementedAiResilience,
)
from better_resume.conversation import (
    ConversationStore,
    Message,
    SessionRef,
    SqlConversationStore,
)
from better_resume.llm_gateway import (
    ChatRequest,
    ChatResult,
    ContentDelta,
    Done,
    LlmGateway,
    ModelSpec,
    OpenAICompatAdapter,
    ReasoningDelta,
    VendorMeta,
)

GATEWAY_SPEC = ModelSpec(
    name="deepseek-flash",
    provider="deepseek",
    base_url="https://api.deepseek.com",
    model_id="deepseek-flash",
    api_key_env="BR_DEEPSEEK_API_KEY",
)

MODULES = ("conversation", "llm_gateway", "ai_resilience")


def params_of(func: object) -> list[str]:
    return list(inspect.signature(func).parameters)  # type: ignore[arg-type]


@pytest.mark.parametrize("module", MODULES)
def test_module_is_importable_from_outside(module: str) -> None:
    assert importlib.import_module(f"better_resume.{module}") is not None


def test_conversation_store_shape() -> None:
    # T1 replaced the M0 placeholder with the Postgres implementation; the protocol
    # conformance check stays (no session is touched by isinstance).
    assert isinstance(SqlConversationStore(session=None), ConversationStore)  # type: ignore[arg-type]
    assert params_of(ConversationStore.append) == ["self", "session", "msg"]
    assert params_of(ConversationStore.history) == ["self", "session", "before", "limit"]
    assert params_of(ConversationStore.require_owner) == ["self", "session", "user_id"]

    ref = SessionRef(kind="interview", session_id="s1")
    assert ref.kind == "interview"
    assert Message(role="user", content="hi").meta == {}


def test_llm_gateway_shape() -> None:
    # T2 replaced the placeholder with the OpenAI-compatible adapter.
    adapter = OpenAICompatAdapter(
        GATEWAY_SPEC,
        api_key="test",
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(200))
        ),
    )
    assert isinstance(adapter, LlmGateway)
    assert params_of(LlmGateway.complete) == ["self", "req"]
    assert params_of(LlmGateway.stream) == ["self", "req"]
    assert inspect.iscoroutinefunction(LlmGateway.complete)
    assert not inspect.iscoroutinefunction(LlmGateway.stream)


class Score(BaseModel):
    value: float


def test_chat_request_carries_schema_contract() -> None:
    req = ChatRequest(messages=[], model_ref="deepseek-v3", response_schema=Score)

    assert req.response_schema is Score
    assert req.model_ref == "deepseek-v3"


def test_stream_event_union_members() -> None:
    events = [ContentDelta(text="a"), ReasoningDelta(text="b"), Done(), VendorMeta(model="m")]
    assert [type(event).__name__ for event in events] == [
        "ContentDelta",
        "ReasoningDelta",
        "Done",
        "VendorMeta",
    ]
    assert ChatResult(content="x", model="m").usage is None


def test_ai_resilience_shape() -> None:
    assert isinstance(UnimplementedAiResilience(), AiResilience)
    assert params_of(AiResilience.run) == ["self", "stage", "key", "fn"]
    assert [stage.value for stage in Stage] == ["extraction", "evaluation", "followup"]


async def test_ai_resilience_placeholder_fails_loudly() -> None:
    resilience = UnimplementedAiResilience()
    with pytest.raises(NotImplementedError):
        await resilience.run(Stage.EVALUATION, "key", _never_called)


async def _never_called() -> str:
    return "unused"
