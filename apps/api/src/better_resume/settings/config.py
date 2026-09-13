"""Application settings (pydantic-settings).

Env vars use the `BR_` prefix; the repo-root `.env` is loaded when present so that a
single file serves both docker compose (repo root) and local `uv run` (apps/api).
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["local", "test", "ci", "production"]

_LOG_LEVELS = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}


class Settings(BaseSettings):
    """Runtime configuration; values are validated at startup."""

    model_config = SettingsConfigDict(
        env_prefix="BR_",
        env_file=(".env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "better-resume-api"
    environment: Environment = "local"
    log_level: str = "INFO"

    # Dev defaults match .env.example / compose; real deployments set these via env.
    database_url: str = Field(
        default="postgresql+asyncpg://better_resume:better_resume@localhost:5432/better_resume"
    )
    redis_url: str = "redis://localhost:6379/0"

    session_cookie_name: str = "br_session"
    session_ttl_seconds: int = 60 * 60 * 24 * 30  # D11: 30 天滑动过期
    session_cookie_secure: bool = False

    request_id_header: str = "X-Request-Id"

    # SSE keep-alive: comment frames every N seconds (old project used 15s).
    sse_heartbeat_seconds: float = 15.0

    # Uploaded resumes live on a local volume, content-addressed by sha256 (Q2 decision).
    resume_storage_dir: Path = Path("data/resumes")

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, value: str) -> str:
        level = value.upper()
        if level not in _LOG_LEVELS:
            raise ValueError(f"log_level must be one of {sorted(_LOG_LEVELS)}, got {value!r}")
        return level

    @field_validator("database_url")
    @classmethod
    def _validate_database_url(cls, value: str) -> str:
        if not value.startswith("postgresql+asyncpg://"):
            raise ValueError("database_url must use the postgresql+asyncpg:// scheme")
        return value

    @field_validator("redis_url")
    @classmethod
    def _validate_redis_url(cls, value: str) -> str:
        if not value.startswith(("redis://", "rediss://", "unix://")):
            raise ValueError("redis_url must use the redis:// scheme")
        return value


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings accessor (FastAPI dependency friendly)."""
    return Settings()
