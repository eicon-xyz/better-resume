"""M4-T3: one-shot WS tickets (D11) — issue, consume once, expire."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from better_resume.identity import InMemoryWsTicketStore, Principal, RedisWsTicketStore


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


async def test_ticket_is_single_use() -> None:
    clock = FakeClock()
    store = InMemoryWsTicketStore(clock=clock)
    principal = Principal(user_id="u1", roles=[])

    ticket = await store.issue(principal, ttl_seconds=30)

    assert await store.consume(ticket) == principal
    assert await store.consume(ticket) is None


async def test_ticket_expires() -> None:
    clock = FakeClock()
    store = InMemoryWsTicketStore(clock=clock)
    ticket = await store.issue(Principal(user_id="u1", roles=[]), ttl_seconds=30)

    clock.now += 31

    assert await store.consume(ticket) is None


async def test_unknown_ticket_is_rejected() -> None:
    store = InMemoryWsTicketStore()
    assert await store.consume("not-a-ticket") is None


async def test_redis_store_is_atomic_and_one_shot(settings) -> None:
    store = RedisWsTicketStore(settings.redis_url)
    try:
        await store._client.ping()  # noqa: SLF001 - skip cleanly when Redis is absent
    except Exception:  # noqa: BLE001
        pytest.skip("redis not reachable")
    try:
        principal = Principal(user_id=f"u-{uuid.uuid4().hex[:6]}", roles=[])
        ticket = await store.issue(principal, ttl_seconds=30)

        assert await store.consume(ticket) == principal
        assert await store.consume(ticket) is None
    finally:
        await store.aclose()


def test_http_issues_a_ticket(client: TestClient) -> None:
    assert client.post("/api/v1/auth/ws-ticket").status_code == 401

    user_id = f"ticket-{uuid.uuid4().hex[:8]}"
    client.post("/api/v1/auth/session", json={"user_id": user_id})
    response = client.post("/api/v1/auth/ws-ticket")

    assert response.status_code == 200
    payload = response.json()
    assert payload["expires_in"] == 30
    assert len(payload["ticket"]) >= 32
