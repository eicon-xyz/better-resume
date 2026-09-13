from __future__ import annotations

import fakeredis.aioredis
import pytest
from fastapi.testclient import TestClient

from better_resume.identity import (
    InMemorySessionStore,
    Principal,
    RedisSessionStore,
    UnimplementedWsTicketStore,
)


class FakeClock:
    def __init__(self, now: float = 1_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_create_session_sets_hardened_cookie(client: TestClient) -> None:
    response = client.post("/api/v1/auth/session", json={"user_id": "u1", "roles": ["candidate"]})

    assert response.status_code == 200
    assert response.json() == {"user_id": "u1", "roles": ["candidate"]}

    cookie = response.headers["set-cookie"]
    assert "br_session=" in cookie
    assert "HttpOnly" in cookie
    assert "samesite=lax" in cookie.lower()
    assert "path=/" in cookie.lower()


def test_me_without_cookie_is_401(client: TestClient) -> None:
    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.json()["detail"] == "not authenticated"


def test_me_returns_principal_with_cookie(client: TestClient) -> None:
    client.post("/api/v1/auth/session", json={"user_id": "u42", "roles": ["candidate"]})

    response = client.get("/api/v1/auth/me")

    assert response.status_code == 200
    assert response.json() == {"user_id": "u42", "roles": ["candidate"]}


def test_logout_invalidates_session(client: TestClient) -> None:
    client.post("/api/v1/auth/session", json={"user_id": "u1"})
    assert client.get("/api/v1/auth/me").status_code == 200

    logout = client.delete("/api/v1/auth/session")
    assert logout.status_code == 204

    assert client.get("/api/v1/auth/me").status_code == 401


async def test_memory_store_slides_expiry_on_touch() -> None:
    clock = FakeClock()
    store = InMemorySessionStore(clock=clock)

    record = await store.create(Principal(user_id="u1"), ttl_seconds=60)

    clock.advance(59)
    assert (await store.get(record.session_id)) is not None

    refreshed = await store.touch(record.session_id, ttl_seconds=60)
    assert refreshed is not None
    assert refreshed.expires_at == clock.now + 60

    clock.advance(59)
    assert (await store.get(record.session_id)) is not None

    clock.advance(61)
    assert (await store.get(record.session_id)) is None


async def test_redis_store_round_trip_sets_ttl() -> None:
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    store = RedisSessionStore("redis://localhost:6379/0", client=client)

    record = await store.create(Principal(user_id="u1", roles=["candidate"]), ttl_seconds=60)
    restored = await store.get(record.session_id)

    assert restored is not None
    assert restored.principal == Principal(user_id="u1", roles=["candidate"])
    assert await client.ttl(f"session:{record.session_id}") > 0

    await store.delete(record.session_id)
    assert (await store.get(record.session_id)) is None
    await store.aclose()


async def test_ws_ticket_placeholder_fails_loudly() -> None:
    store = UnimplementedWsTicketStore()

    with pytest.raises(NotImplementedError):
        await store.issue(Principal(user_id="u1"), ttl_seconds=30)
