"""Conversation value objects (§12.2).

D09 drops the standalone agent session, so `SessionKind` is chat | interview.
"""

from __future__ import annotations

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
    role: MessageRole
    content: str
    reasoning: str | None = None
    created_at: float | None = None
    meta: dict[str, Any] = Field(default_factory=dict)
