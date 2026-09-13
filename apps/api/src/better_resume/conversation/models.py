"""Conversation value objects (§12.2).

D09 drops the standalone agent session, so `SessionKind` is chat | interview.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

SessionKind = Literal["chat", "interview"]
SessionId = str
UserId = str
MessageRole = Literal["system", "user", "assistant", "tool"]


class SessionRef(BaseModel):
    """Address of a conversation: (kind, session_id)."""

    kind: SessionKind
    session_id: SessionId


class Message(BaseModel):
    """A message to append (input side)."""

    role: MessageRole
    content: str
    reasoning: str | None = None
    created_at: float | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class StoredMessage(BaseModel):
    """A persisted message (output side): adds seq/token/error bookkeeping."""

    id: str
    seq: int
    role: MessageRole
    content: str
    reasoning: str | None = None
    token_count: int | None = None
    error_message: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class Conversation(BaseModel):
    """A conversation header row."""

    id: SessionId
    kind: SessionKind
    user_id: UserId
    title: str
    model_ref: str | None = None
    message_count: int = 0
    meta: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
