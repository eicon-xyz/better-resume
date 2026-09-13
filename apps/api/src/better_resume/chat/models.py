"""Chat wire models and stream event union."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from ..llm_gateway import ContentDelta, Done, ReasoningDelta, VendorMeta


class ChatSessionCreateRequest(BaseModel):
    title: str = Field(default="", max_length=200)
    model_ref: str | None = Field(default=None, max_length=64)


class SessionUpdateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class StreamRequest(BaseModel):
    """One user turn. `client_message_id` makes resends idempotent (and free)."""

    content: str = Field(min_length=1, max_length=8000)
    model_ref: str | None = Field(default=None, max_length=64)
    client_message_id: str | None = Field(default=None, max_length=64)


class ChatSessionView(BaseModel):
    id: str
    kind: str
    title: str
    model_ref: str | None = None
    message_count: int
    created_at: datetime
    updated_at: datetime


class ChatMessageView(BaseModel):
    id: str
    seq: int
    role: str
    client_message_id: str | None = None
    content: str
    reasoning: str | None = None
    token_count: int | None = None
    error_message: str | None = None
    created_at: datetime


class ChatErrorEvent(BaseModel):
    """Terminal error frame; the partial answer is already persisted when it is sent.

    Kinds cover both taxonomies: llm-gateway's own (retryable/non_retryable/vendor) and
    M3's resilience taxonomy (timeout/overloaded/unavailable/invalid). Missing a value
    here used to crash the SSE producer into "unknown" — see PROBLEMS P8.
    """

    message: str
    kind: Literal[
        "retryable",
        "non_retryable",
        "vendor",
        "timeout",
        "overloaded",
        "unavailable",
        "invalid",
        "duplicate_request",
        "unknown",
    ] = "unknown"


ChatStreamEvent = ContentDelta | ReasoningDelta | VendorMeta | Done | ChatErrorEvent
