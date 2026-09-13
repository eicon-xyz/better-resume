"""Shared helpers for database-backed tests (real Postgres, no mocks)."""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

API_ROOT = Path(__file__).resolve().parents[1]


def alembic_config() -> Config:
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(API_ROOT / "migrations"))
    return config


async def can_connect(database_url: str) -> bool:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            await connection.execute(text("select 1"))
    except Exception:  # noqa: BLE001 - any driver/connection error means "no database here"
        return False
    finally:
        await engine.dispose()
    return True
