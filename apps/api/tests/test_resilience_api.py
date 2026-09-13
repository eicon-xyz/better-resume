"""M3-T7: GET /api/v1/resilience/stats is a session-guarded snapshot."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient


def login(client: TestClient) -> str:
    user_id = f"resilience-{uuid.uuid4().hex[:8]}"
    assert client.post("/api/v1/auth/session", json={"user_id": user_id}).status_code == 200
    return user_id


def test_stats_require_a_session(client: TestClient) -> None:
    assert client.get("/api/v1/resilience/stats").status_code == 401


def test_stats_report_the_guard_chain(client: TestClient, migrated_database: str) -> None:
    login(client)

    response = client.get("/api/v1/resilience/stats")

    assert response.status_code == 200
    payload = response.json()
    assert payload["enabled"] is True
    assert payload["policies"]["evaluation"]["timeout"] == 20.0
    assert payload["policies"]["chat"]["is_stream"] is True
    assert set(payload["policies"]) == {"chat", "extraction", "evaluation", "followup"}
    assert payload["singleflight"]["entries"] == 0
    assert "singleflight_leader" in payload["metrics"]
