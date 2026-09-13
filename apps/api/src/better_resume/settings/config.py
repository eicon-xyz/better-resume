"""Application settings (pydantic-settings).

Env vars use the `BR_` prefix; the repo-root `.env` is loaded when present so that a
single file serves both docker compose (repo root) and local `uv run` (apps/api).
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["local", "test", "ci", "production"]

_LOG_LEVELS = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}


class ResilienceSettings(BaseModel):
    """M3 ai-resilience budgets (§4.1.4 table, plus a chat row the old project lacked)."""

    enabled: bool = True

    chat_timeout_seconds: float = 180.0
    extraction_timeout_seconds: float = 60.0
    evaluation_timeout_seconds: float = 20.0
    followup_timeout_seconds: float = 20.0

    chat_max_concurrency: int = 16
    extraction_max_concurrency: int = 8
    evaluation_max_concurrency: int = 30
    followup_max_concurrency: int = 20
    queue_wait_seconds: float = 2.0

    # Completed-call replay: 0 disables it for that stage (chat must never replay).
    chat_replay_seconds: float = 0.0
    evaluation_replay_seconds: float = 60.0
    followup_replay_seconds: float = 60.0
    extraction_replay_seconds: float = 300.0
    negative_cache_seconds: float = 10.0

    breaker_window: int = 50
    breaker_min_calls: int = 10
    breaker_failure_rate: float = 0.5
    breaker_open_seconds: float = 30.0
    breaker_half_open_permits: int = 10

    singleflight_max_entries: int = 256
    stream_buffer_frames: int = 1024


class RateLimitSettings(BaseModel):
    """M3 in-process flow limiting (old project's flow-limit matrix)."""

    enabled: bool = True
    general_per_second: float = 20.0
    read_per_second: float = 15.0
    answer_per_second: float = 8.0
    heavy_per_second: float = 2.0
    ai_call_per_second: float = 6.0
    burst_multiplier: float = 2.0


class Settings(BaseSettings):
    """Runtime configuration; values are validated at startup."""

    model_config = SettingsConfigDict(
        env_prefix="BR_",
        env_file=(".env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        # Nested blocks read BR_RESILIENCE__BREAKER_WINDOW etc. (M3).
        env_nested_delimiter="__",
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

    # M3: resilience budgets and in-process rate limiting.
    resilience: ResilienceSettings = Field(default_factory=ResilienceSettings)
    rate_limit: RateLimitSettings = Field(default_factory=RateLimitSettings)

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
