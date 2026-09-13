"""T2: /api/v1/models exposes the registry without leaking credentials."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_models_endpoint_requires_a_session(client: TestClient) -> None:
    assert client.get("/api/v1/models").status_code == 401


def login(client: TestClient) -> None:
    response = client.post("/api/v1/auth/session", json={"user_id": "models-user"})
    assert response.status_code == 200


def test_models_endpoint_lists_seeded_models(client: TestClient, migrated_database: str) -> None:
    login(client)

    response = client.get("/api/v1/models")

    assert response.status_code == 200
    models = response.json()
    assert [model["name"] for model in models] == ["deepseek-flash", "deepseek-v4-pro"]
    assert models[0]["is_default"] is True
    assert models[0]["supports_reasoning"] is True
    # Hermetic tests have no key configured: the API must say so instead of pretending.
    assert all(model["configured"] is False for model in models)
    assert "api_key" not in response.text


def test_models_endpoint_reports_configured_key(
    client: TestClient, migrated_database: str, monkeypatch
) -> None:
    monkeypatch.setenv("BR_DEEPSEEK_API_KEY", "sk-test-not-real")
    login(client)

    models = client.get("/api/v1/models").json()

    assert all(model["configured"] is True for model in models)
