"""Auth endpoints: dev-issued session, me, logout, and one-shot WS tickets (D11)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, Field

from ..settings import Settings
from .cookies import clear_session_cookie, set_session_cookie
from .deps import current_principal, get_app_settings, get_session_store, get_ws_ticket_store
from .models import Principal
from .store import SessionStore
from .tickets import WsTicketStore

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class AuthSessionRequest(BaseModel):
    """Dev-issued session body (real credential login arrives in M2)."""

    user_id: str = Field(min_length=1, max_length=128)
    roles: list[str] = Field(default_factory=list)


class WsTicketView(BaseModel):
    """Short-lived, single-use ticket for the WebSocket handshake."""

    ticket: str
    expires_in: int


@router.post("/session")
async def create_session(
    payload: AuthSessionRequest,
    response: Response,
    settings: Settings = Depends(get_app_settings),  # noqa: B008
    store: SessionStore = Depends(get_session_store),  # noqa: B008
) -> Principal:
    record = await store.create(
        Principal(user_id=payload.user_id, roles=payload.roles),
        ttl_seconds=settings.session_ttl_seconds,
    )
    set_session_cookie(response, settings=settings, session_id=record.session_id)
    return record.principal


@router.get("/me")
async def me(principal: Principal = Depends(current_principal)) -> Principal:  # noqa: B008
    return principal


@router.post("/ws-ticket")
async def create_ws_ticket(
    principal: Principal = Depends(current_principal),  # noqa: B008
    settings: Settings = Depends(get_app_settings),  # noqa: B008
    tickets: WsTicketStore = Depends(get_ws_ticket_store),  # noqa: B008
) -> WsTicketView:
    """Browsers cannot set headers on a WebSocket, so the cookie buys a one-shot ticket."""
    ttl = settings.ws_ticket_ttl_seconds
    ticket = await tickets.issue(principal, ttl_seconds=ttl)
    return WsTicketView(ticket=ticket, expires_in=ttl)


@router.delete("/session", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    request: Request,
    response: Response,
    settings: Settings = Depends(get_app_settings),  # noqa: B008
    store: SessionStore = Depends(get_session_store),  # noqa: B008
) -> None:
    session_id = request.cookies.get(settings.session_cookie_name)
    if session_id:
        await store.delete(session_id)
    clear_session_cookie(response, settings=settings)
