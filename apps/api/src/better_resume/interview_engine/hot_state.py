"""Session hot state (M6-T3): a Redis cache for the restore view, nothing more.

Postgres stays the single source of truth. This layer exists so a second api instance can
answer `/restore` without re-deriving the whole interview, and so a killed instance does not
cost the user their session. Two documented rules keep it honest:

* writes invalidate (never update in place) — a stale view is worse than a slow one;
* every view says where it came from (`source="hot"` vs `"derived"`), so callers can tell.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

import redis.asyncio as aioredis
import structlog

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .restore_service import RestoreView

logger = structlog.get_logger("better_resume.interview_engine.hot_state")

HotSource = Literal["hot", "derived"]


def _key(user_id: str, session_id: str) -> str:
    # User-scoped on purpose: a cache hit must never cross an ownership boundary.
    return f"br:hot:restore:{user_id}:{session_id}"


@runtime_checkable
class HotStateStore(Protocol):
    async def get(self, *, user_id: str, session_id: str) -> RestoreView | None: ...

    async def put(self, view: RestoreView, *, user_id: str, ttl_seconds: int) -> None: ...

    async def invalidate(self, *, user_id: str, session_id: str) -> None: ...

    async def aclose(self) -> None: ...


class InMemoryHotState:
    """Test/dev backend; TTL is wall-clock (no fake clock: Redis expires on wall-clock too)."""

    def __init__(self, *, clock: object | None = None) -> None:
        self._entries: dict[str, tuple[str, float]] = {}
        self._clock = clock

    def _now(self) -> float:
        import time

        if self._clock is not None:
            return float(self._clock.now())  # type: ignore[attr-defined]
        return time.monotonic()

    async def get(self, *, user_id: str, session_id: str) -> RestoreView | None:
        from .restore_service import RestoreView

        entry = self._entries.get(_key(user_id, session_id))
        if entry is None:
            return None
        payload, expires_at = entry
        if expires_at <= self._now():
            self._entries.pop(_key(user_id, session_id), None)
            return None
        # Both backends must answer identically: a hit is always source="hot".
        return RestoreView.model_validate_json(payload).model_copy(update={"source": "hot"})

    async def put(self, view: RestoreView, *, user_id: str, ttl_seconds: int) -> None:
        self._entries[_key(user_id, view.session.id)] = (
            view.model_dump_json(),
            self._now() + max(0, ttl_seconds),
        )

    async def invalidate(self, *, user_id: str, session_id: str) -> None:
        self._entries.pop(_key(user_id, session_id), None)

    async def aclose(self) -> None:
        self._entries.clear()


class RedisHotState:
    def __init__(self, redis_url: str, *, ttl_seconds: int = 600) -> None:
        self._client = aioredis.from_url(redis_url, decode_responses=True)
        self._ttl = max(1, ttl_seconds)

    async def get(self, *, user_id: str, session_id: str) -> RestoreView | None:
        from .restore_service import RestoreView

        try:
            raw = await self._client.get(_key(user_id, session_id))
        except Exception as exc:  # noqa: BLE001 - the cache must never break a request
            logger.warning("hot_state_get_failed", error=str(exc))
            return None
        if not raw:
            return None
        try:
            view = RestoreView.model_validate_json(raw)
        except ValueError as exc:
            logger.warning("hot_state_unreadable", error=str(exc))
            return None
        return view.model_copy(update={"source": "hot"})

    async def put(self, view: RestoreView, *, user_id: str, ttl_seconds: int) -> None:
        try:
            await self._client.set(
                _key(user_id, view.session.id),
                view.model_dump_json(),
                ex=max(1, ttl_seconds or self._ttl),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("hot_state_put_failed", error=str(exc))

    async def invalidate(self, *, user_id: str, session_id: str) -> None:
        try:
            await self._client.delete(_key(user_id, session_id))
        except Exception as exc:  # noqa: BLE001
            logger.warning("hot_state_invalidate_failed", error=str(exc))

    async def aclose(self) -> None:
        await self._client.aclose()


def build_hot_state(settings: object) -> HotStateStore:
    """memory by default (single process), Redis once there is more than one instance."""
    backend = getattr(settings, "hot_state_backend", "memory")
    ttl = int(getattr(settings, "hot_state_ttl_seconds", 600))
    if backend == "redis":
        return RedisHotState(settings.redis_url, ttl_seconds=ttl)
    return InMemoryHotState()
