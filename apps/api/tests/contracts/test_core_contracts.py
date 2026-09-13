"""Contract smoke tests for conversation / llm-gateway / ai-resilience (§12.2 signatures)."""

from __future__ import annotations

import importlib
import inspect

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
    UnimplementedConversationStore,
)
from better_resume.llm_gateway import (
    ChatRequest,
    ChatResult,
    ContentDelta,
    Done,
    LlmGateway,
    ReasoningDelta,
    UnimplementedLlmGateway,
    VendorMeta,
)

MODULES = ("conversation", "llm_gateway", "ai_resilience")


def params_of(func: object) -> list[str]:
    return list(inspect.signature(func).parameters)  # type: ignore[arg-type]


@pytest.mark.parametrize("module", MODULES)
def test_module_is_importable_from_outside(module: str) -> None:
    assert importlib.import_module(f"better_resume.{module}") is not None


def test_conversation_store_shape() -> None:
    assert isinstance(UnimplementedConversationStore(), ConversationStore)
    assert params_of(ConversationStore.append) == ["self", "session", "msg"]
    assert params_of(ConversationStore.history) == ["self", "session", "before", "limit"]
    assert params_of(ConversationStore.require_owner) == ["self", "session", "user_id"]

    ref = SessionRef(kind="interview", session_id="s1")
    assert ref.kind == "interview"
    assert Message(role="user", content="hi").meta == {}


async def test_conversation_placeholder_fails_loudly() -> None:
    store = UnimplementedConversationStore()
    with pytest.raises(NotImplementedError):
        await store.append(
            SessionRef(kind="chat", session_id="s1"), Message(role="user", content="hi")
        )


def test_llm_gateway_shape() -> None:
    assert isinstance(UnimplementedLlmGateway(), LlmGateway)
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


async def test_llm_gateway_placeholder_fails_loudly() -> None:
    gateway = UnimplementedLlmGateway()
    with pytest.raises(NotImplementedError):
        await gateway.complete(ChatRequest(messages=[]))
    with pytest.raises(NotImplementedError):
        gateway.stream(ChatRequest(messages=[]))


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
