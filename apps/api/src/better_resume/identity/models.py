"""Identity value objects (D11: cookie session, no JWT)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Principal(BaseModel):
    """The authenticated subject of a session."""

    user_id: str
    roles: list[str] = Field(default_factory=list)


class SessionRecord(BaseModel):
    """Server-side session payload (stored in Redis, keyed by session id)."""

    session_id: str
    principal: Principal
    created_at: float
    expires_at: float
