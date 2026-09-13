"""llm-gateway value objects: one request shape for every vendor (§12.2)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Role = Literal["system", "user", "assistant", "tool"]


class Message(BaseModel):
    role: Role
    content: str


class VendorContext(BaseModel):
    """Passthrough for the Xingyun workflow adapter vs local orchestration."""

    vendor: str
    workflow_id: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)


class TokenUsage(BaseModel):
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


class ChatRequest(BaseModel):
    """`response_schema` carries the structured-output contract (scoring/questions/follow-ups)."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    messages: list[Message]
    model_ref: str | None = None
    response_schema: type[BaseModel] | None = None
    vendor_ctx: VendorContext | None = None


class ChatResult(BaseModel):
    content: str
    model: str
    reasoning: str | None = None
    usage: TokenUsage | None = None
    raw_response: dict[str, Any] | None = None


class ContentDelta(BaseModel):
    text: str


class ReasoningDelta(BaseModel):
    text: str


class Done(BaseModel):
    finish_reason: str | None = None


class VendorMeta(BaseModel):
    model: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


StreamEvent = ContentDelta | ReasoningDelta | Done | VendorMeta
