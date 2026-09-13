from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from better_resume.main import create_app
from better_resume.settings import Settings


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
