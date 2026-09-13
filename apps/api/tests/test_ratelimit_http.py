"""M3-T6: the middleware surface — 429, headers, identity isolation, fail-open."""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from better_resume.ai_resilience import ManualClock, RateLimiter
from better_resume.main import create_app
from better_resume.settings import RateLimitSettings, Settings


def tight_settings(settings: Settings, **overrides: object) -> Settings:
    limits = RateLimitSettings(
        enabled=True,
        general_per_second=2.0,
        read_per_second=2.0,
        answer_per_second=1.0,
        heavy_per_second=1.0,
        ai_call_per_second=1.0,
        burst_multiplier=1.0,
    )
    limits = limits.model_copy(update=overrides or {})
    return settings.model_copy(update={"rate_limit": limits})


@pytest.fixture
def clock() -> ManualClock:
    return ManualClock()


@pytest.fixture
def tight_app(settings: Settings) -> FastAPI:
    return create_app(tight_settings(settings))


@pytest.fixture
def tight_client(tight_app: FastAPI, clock: ManualClock) -> Iterator[TestClient]:
    with TestClient(tight_app) as client:
        # Swap the limiter for one driven by the manual clock (lifespan built the real one).
        client.app.state.rate_limiter = RateLimiter(
            tight_app.state.settings.rate_limit, clock=clock
        )
        yield client


def login(client: TestClient) -> str:
    user_id = f"ratelimit-{uuid.uuid4().hex[:8]}"
    assert client.post("/api/v1/auth/session", json={"user_id": user_id}).status_code == 200
    return user_id


def test_healthz_is_never_limited(tight_client: TestClient) -> None:
    for _ in range(100):
        assert tight_client.get("/healthz").status_code == 200
    assert "X-RateLimit-Bucket" not in tight_client.get("/healthz").headers


def test_read_bucket_blocks_then_refills_on_the_clock(
    tight_client: TestClient, clock: ManualClock
) -> None:
    assert tight_client.get("/api/v1/models").status_code in (200, 401)
    ok = tight_client.get("/api/v1/models")
    assert ok.status_code in (200, 401)
    assert ok.headers["X-RateLimit-Bucket"] == "read"
    assert ok.headers["X-RateLimit-Remaining"] == "0"

    blocked = tight_client.get("/api/v1/models")
    assert blocked.status_code == 429
    assert blocked.headers["Retry-After"] == "1"
    assert blocked.headers["X-RateLimit-Bucket"] == "read"
    body = blocked.json()
    assert body["bucket"] == "read"
    assert body["retry_after"] == 1
    assert blocked.headers.get("x-request-id")  # request id still attached

    clock.advance(1.0)
    assert tight_client.get("/api/v1/models").status_code in (200, 401)


def test_identities_are_isolated(tight_client: TestClient) -> None:
    tight_client.cookies.set("br_session", "session-a")
    assert tight_client.get("/api/v1/models").status_code in (200, 401)
    assert tight_client.get("/api/v1/models").status_code in (200, 401)
    assert tight_client.get("/api/v1/models").status_code == 429

    tight_client.cookies.set("br_session", "session-b")
    assert tight_client.get("/api/v1/models").status_code in (200, 401)


def test_anonymous_callers_fall_back_to_the_client_address(tight_client: TestClient) -> None:
    for _ in range(2):
        assert tight_client.get("/api/v1/chat/sessions").status_code == 401
    assert tight_client.get("/api/v1/chat/sessions").status_code == 429


def test_buckets_are_isolated(tight_client: TestClient) -> None:
    login(tight_client)
    for _ in range(2):
        assert tight_client.get("/api/v1/models").status_code == 200
    assert tight_client.get("/api/v1/models").status_code == 429

    # a POST goes to the general bucket and is unaffected by the exhausted read bucket
    assert tight_client.post("/api/v1/chat/sessions", json={}).status_code != 429


def test_answer_and_ai_call_buckets_are_classified(tight_client: TestClient) -> None:
    login(tight_client)
    session_id = uuid.uuid4().hex
    first = tight_client.post(f"/api/v1/interview/sessions/{session_id}/answers", json={})
    assert first.headers.get("X-RateLimit-Bucket") == "answer"
    second = tight_client.post(f"/api/v1/interview/sessions/{session_id}/answers", json={})
    assert second.status_code == 429

    stream = tight_client.post(f"/api/v1/chat/sessions/{session_id}/stream", json={"content": "hi"})
    assert stream.headers.get("X-RateLimit-Bucket") == "ai_call"


def test_disabled_limiter_never_blocks(settings: Settings, clock: ManualClock) -> None:
    app = create_app(tight_settings(settings, enabled=False))
    with TestClient(app) as client:
        client.app.state.rate_limiter = RateLimiter(app.state.settings.rate_limit, clock=clock)
        for _ in range(20):
            assert client.get("/api/v1/models").status_code in (200, 401)


def test_middleware_fails_open_on_its_own_bugs(
    tight_app: FastAPI, clock: ManualClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    with TestClient(tight_app) as client:
        limiter = RateLimiter(tight_app.state.settings.rate_limit, clock=clock)

        def explode(*args: object, **kwargs: object) -> None:
            raise RuntimeError("limiter bug")

        monkeypatch.setattr(limiter, "check", explode)
        client.app.state.rate_limiter = limiter
        for _ in range(5):
            assert client.get("/api/v1/models").status_code in (200, 401)
