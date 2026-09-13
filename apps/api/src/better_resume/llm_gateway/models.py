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
    reasoning_tokens: int | None = None


class ModelSpec(BaseModel):
    """One row of the model registry; the API key itself is only referenced by env name."""

    name: str
    provider: str
    base_url: str
    model_id: str
    api_key_env: str
    max_tokens: int = 2048
    temperature: float = 0.7
    system_prompt: str | None = None
    supports_reasoning: bool = False
    is_enabled: bool = True
    priority: int = 100
    extra: dict[str, Any] = Field(default_factory=dict)


class ModelView(BaseModel):
    """Public projection of a registry row (never contains credentials)."""

    name: str
    model_id: str
    provider: str
    supports_reasoning: bool
    configured: bool
    is_default: bool = False


class ChatRequest(BaseModel):
    """`response_schema` carries the structured-output contract (scoring/questions/follow-ups)."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    messages: list[Message]
    model_ref: str | None = None
    response_schema: type[BaseModel] | None = None
    vendor_ctx: VendorContext | None = None
    max_tokens: int | None = None
    temperature: float | None = None


class ChatResult(BaseModel):
    content: str
    model: str
    reasoning: str | None = None
    usage: TokenUsage | None = None
    raw_response: dict[str, Any] | None = None
    parsed: BaseModel | None = None


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
