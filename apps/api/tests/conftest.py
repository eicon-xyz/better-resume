from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from better_resume.main import create_app
from better_resume.settings import Settings, get_settings


@pytest.fixture(scope="session")
def ambient_br_env() -> dict[str, str]:
    """BR_* variables inherited from the shell/CI, captured before tests go hermetic."""
    return {key: value for key, value in os.environ.items() if key.startswith("BR_")}


@pytest.fixture(autouse=True)
def hermetic_br_env(
    monkeypatch: pytest.MonkeyPatch, ambient_br_env: dict[str, str]
) -> Iterator[None]:
    """Tests never depend on the developer's or CI's ambient BR_* configuration."""
    for key in ambient_br_env:
        monkeypatch.delenv(key, raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def settings() -> Settings:
    """Test settings: ignore any .env on disk so tests are hermetic."""
    return Settings(_env_file=None, environment="test", log_level="WARNING")


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
