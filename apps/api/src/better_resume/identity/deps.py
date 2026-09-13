"""FastAPI dependencies for the identity module."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status

from ..settings import Settings
from .models import Principal
from .store import SessionStore


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings  # type: ignore[no-any-return]


def get_session_store(request: Request) -> SessionStore:
    return request.app.state.session_store  # type: ignore[no-any-return]


async def current_principal(
    request: Request,
    settings: Settings = Depends(get_app_settings),  # noqa: B008
) -> Principal:
    """Resolve the session cookie into a principal; 401 when missing or expired."""
    store = get_session_store(request)
    session_id = request.cookies.get(settings.session_cookie_name)
    if not session_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated")

    record = await store.touch(session_id, ttl_seconds=settings.session_ttl_seconds)
    if record is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="session expired")
    return record.principal
