from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from better_resume.settings import Settings


def test_healthz_returns_ok(client: TestClient) -> None:
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["content-type"].startswith("application/json")


def test_app_exposes_settings_on_state(app: FastAPI) -> None:
    assert isinstance(app.state.settings, Settings)


def test_request_id_header_is_always_present(client: TestClient) -> None:
    response = client.get("/healthz")

    assert response.headers.get("X-Request-Id")
