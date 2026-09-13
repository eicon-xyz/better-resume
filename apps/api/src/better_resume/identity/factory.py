"""Wire the session store from settings (Redis in real environments, memory in tests)."""

from __future__ import annotations

from ..settings import Settings
from .memory_store import InMemorySessionStore
from .redis_store import RedisSessionStore
from .store import SessionStore


def build_session_store(settings: Settings) -> SessionStore:
    if settings.environment == "test":
        return InMemorySessionStore()
    return RedisSessionStore(settings.redis_url)
