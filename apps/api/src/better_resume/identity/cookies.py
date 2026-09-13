"""Cookie helpers: all session cookie policy lives here (D11)."""

from __future__ import annotations

from fastapi import Response

from ..settings import Settings


def set_session_cookie(response: Response, *, settings: Settings, session_id: str) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=session_id,
        max_age=settings.session_ttl_seconds,
        httponly=True,
        samesite="lax",
        secure=settings.session_cookie_secure,
        path="/",
    )


def clear_session_cookie(response: Response, *, settings: Settings) -> None:
    response.delete_cookie(key=settings.session_cookie_name, path="/")
