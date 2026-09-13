from __future__ import annotations

import asyncio
import os
from collections.abc import Iterator

import pytest
import redis.asyncio as aioredis
from alembic import command
from fastapi import FastAPI
from fastapi.testclient import TestClient

from better_resume.main import create_app
from better_resume.settings import Settings, get_settings

from .db_utils import alembic_config, can_connect


@pytest.fixture(scope="session")
def ambient_br_env() -> dict[str, str]:
    """BR_* variables inherited from the shell/CI, captured before tests go hermetic."""
    return {key: value for key, value in os.environ.items() if key.startswith("BR_")}


@pytest.fixture(scope="session")
def database_url(ambient_br_env: dict[str, str]) -> str:
    return ambient_br_env.get("BR_DATABASE_URL") or Settings(_env_file=None).database_url


@pytest.fixture(scope="session")
def migrated_database(database_url: str) -> str:
    """Bring the database to head once per session; skip when Postgres is unreachable."""
    if not asyncio.run(can_connect(database_url)):
        pytest.skip(f"postgres not reachable at {database_url}")

    previous = os.environ.get("BR_DATABASE_URL")
    os.environ["BR_DATABASE_URL"] = database_url
    get_settings.cache_clear()
    try:
        command.upgrade(alembic_config(), "head")
    finally:
        if previous is None:
            os.environ.pop("BR_DATABASE_URL", None)
        else:
            os.environ["BR_DATABASE_URL"] = previous
        get_settings.cache_clear()
    return database_url


@pytest.fixture
def redis_url(ambient_br_env: dict[str, str]) -> str:
    """The Redis the tests use; the test is skipped when it is unreachable."""
    url = ambient_br_env.get("BR_REDIS_URL") or "redis://127.0.0.1:6379/0"

    async def reachable() -> bool:
        client = aioredis.from_url(url, decode_responses=True)
        try:
            await asyncio.wait_for(client.ping(), timeout=2.0)
            return True
        finally:
            await client.aclose()

    try:
        ok = asyncio.run(reachable())
    except Exception:  # noqa: BLE001 - any connection problem means "skip"
        ok = False
    if not ok:
        pytest.skip(f"redis not reachable at {url}")
    return url


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
def settings(database_url: str) -> Settings:
    """Test settings: ignore any .env on disk, and point the app at the test database.

    Without the explicit URL the app would fall back to the built-in localhost:5432 default,
    which is right in CI but wrong whenever a developer runs Postgres elsewhere.
    """
    return Settings(
        _env_file=None,
        environment="test",
        log_level="WARNING",
        database_url=database_url,
    )


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
