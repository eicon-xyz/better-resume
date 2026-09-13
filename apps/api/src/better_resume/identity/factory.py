"""Wire the session and WS-ticket stores from settings."""

from __future__ import annotations

from ..settings import Settings
from .memory_store import InMemorySessionStore
from .redis_store import RedisSessionStore
from .store import SessionStore
from .tickets import InMemoryWsTicketStore, RedisWsTicketStore, WsTicketStore


def build_session_store(settings: Settings) -> SessionStore:
    if settings.environment == "test":
        return InMemorySessionStore()
    return RedisSessionStore(settings.redis_url)


def build_ws_ticket_store(settings: Settings) -> WsTicketStore:
    if settings.environment == "test":
        return InMemoryWsTicketStore()
    return RedisWsTicketStore(settings.redis_url)
