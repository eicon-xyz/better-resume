"""V6: a Redis outage must surface as 503, never as an unhandled 500.

Found by the fault-injection drill: with Redis restarting, `/api/v1/auth/me` returned 500
because the session store's connection error escaped the endpoint. Losing the session key is
a 401 (the browser must log in again), but being *unable to ask* is a 503 with Retry-After —
the client should not be told to log in when logging in would fail too.
"""

from __future__ import annotations

import pytest
import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.testclient import TestClient

from better_resume.identity import RedisSessionStore, SessionBackendUnavailable


class BrokenRedis:
    """Stands in for a Redis that is restarting: every command raises."""

    def __init__(self) -> None:
        self.error = aioredis.ConnectionError("connection refused")

    async def get(self, key: str) -> str | None:
        raise self.error

    async def set(self, *args: object, **kwargs: object) -> None:
        raise self.error

    async def delete(self, key: str) -> None:
        raise self.error


async def test_store_translates_redis_errors() -> None:
    store = RedisSessionStore("redis://127.0.0.1:6379/0", client=BrokenRedis())  # type: ignore[arg-type]

    with pytest.raises(SessionBackendUnavailable):
        await store.get("session-1")

    with pytest.raises(SessionBackendUnavailable):
        await store.create(principal=_principal(), ttl_seconds=60)


def _principal():
    from better_resume.identity import Principal

    return Principal(user_id="v6")


def test_missing_session_still_means_401(app: FastAPI, client: TestClient) -> None:
    client.cookies.set("br_session", "does-not-exist")

    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401


def test_redis_outage_is_503_with_retry_after(
    app: FastAPI, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    class UnavailableStore:
        async def get(self, session_id: str):
            raise SessionBackendUnavailable("session store is unavailable")

        async def touch(self, session_id: str, *, ttl_seconds: int):
            raise SessionBackendUnavailable("session store is unavailable")

        async def create(self, principal, *, ttl_seconds: int):  # noqa: ANN001, ANN202
            raise SessionBackendUnavailable("session store is unavailable")

        async def delete(self, session_id: str) -> None:
            raise SessionBackendUnavailable("session store is unavailable")

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr(app.state, "session_store", UnavailableStore(), raising=False)
    client.cookies.set("br_session", "whatever")

    response = client.get("/api/v1/auth/me")

    assert response.status_code == 503, response.text
    assert "unavailable" in response.json()["detail"]
    assert response.headers["retry-after"] == "5"
