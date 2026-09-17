"""Application settings (pydantic-settings).

Env vars use the `BR_` prefix; the repo-root `.env` is loaded when present so that a
single file serves both docker compose (repo root) and local `uv run` (apps/api).
"""

from __future__ import annotations

import functools
import socket
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
    tts_timeout_seconds: float = 20.0

    chat_max_concurrency: int = 16
    extraction_max_concurrency: int = 8
    evaluation_max_concurrency: int = 30
    followup_max_concurrency: int = 20
    queue_wait_seconds: float = 2.0
    tts_max_concurrency: int = 8

    # Completed-call replay: 0 disables it for that stage (chat must never replay).
    chat_replay_seconds: float = 0.0
    evaluation_replay_seconds: float = 60.0
    followup_replay_seconds: float = 60.0
    extraction_replay_seconds: float = 300.0
    tts_replay_seconds: float = 300.0
    negative_cache_seconds: float = 10.0

    breaker_window: int = 50
    breaker_min_calls: int = 10
    breaker_failure_rate: float = 0.5
    breaker_open_seconds: float = 30.0
    breaker_half_open_permits: int = 10

    singleflight_max_entries: int = 256

    # M6: cross-instance single flight (Redis). Off by default; the kill
    # drill exercises it, so it is not a dead branch.
    distributed: bool = False
    flight_lease_seconds: float = 30.0
    flight_wait_seconds: float = 10.0
    flight_poll_seconds: float = 0.1
    stream_buffer_frames: int = 1024


class MediaSettings(BaseModel):
    """M4 media wiring: which transcription adapter, and how TTS behaves."""

    #: scripted (CI/local) | xunfei (AST websocket) | qwen-asr (Aliyun Bailian batch ASR)
    #: | paraformer-rt (Bailian realtime ASR, incremental)
    transcription_adapter: Literal["xunfei", "scripted", "qwen-asr", "paraformer-rt"] = "scripted"
    #: MaaS workspace endpoint for qwen-audio-3.0-asr-flash; account specific, so env only.
    asr_url: str = ""
    asr_model: str = "qwen-audio-3.0-asr-flash"
    asr_timeout_seconds: float = 30.0
    #: P1-A realtime recognition: explicit wss endpoint; empty = derive the wss:// host
    #: from asr_url (same workspace domain, fixed /api-ws/v1/inference path).
    asr_ws_url: str = ""
    asr_realtime_model: str = "paraformer-realtime-v2"
    xunfei_ws_url: str = "wss://office-api-ast-dx.iflyaisol.com/ast/communicate/v1"
    tts_voice: str = "zh-CN-XiaoxiaoNeural"
    tts_storage_dir: Path = Path("data/tts")
    tts_max_chars: int = 500


class RateLimitSettings(BaseModel):
    """M3 in-process flow limiting (old project's flow-limit matrix)."""

    enabled: bool = True
    general_per_second: float = 20.0
    read_per_second: float = 15.0
    # P1-B 标定（2026-09-15，docs/perf/M6-capacity.md §2.7）：真实单用户 answer ~0.2 rps、
    # chat 流 ~0.5 rps；旧值（8/6）曾允许单身份经 2 副本维持 24 并发供应商流。
    answer_per_second: float = 2.0
    heavy_per_second: float = 2.0
    ai_call_per_second: float = 2.0
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
    media: MediaSettings = Field(default_factory=MediaSettings)

    # M4: D11 one-shot WS ticket lifetime, plus vendor credentials (env only).
    ws_ticket_ttl_seconds: int = 30

    # M6: question locks and other cross-instance coordination.
    lock_backend: Literal["memory", "redis"] = "memory"
    lock_ttl_seconds: float = 30.0
    lock_wait_seconds: float = 10.0
    hot_state_backend: Literal["memory", "redis"] = "memory"
    hot_state_ttl_seconds: int = 600

    # M6/V1: scene bindings are cached per process, so an admin change only reaches
    # the other replicas after this TTL (0 disables the cache entirely).
    scene_binding_cache_seconds: float = 5.0

    # M6: which container answered. Compose sets it per replica; the default is the host.
    instance_id: str = Field(default_factory=socket.gethostname)

    # M6: background jobs. Off by default (single-process dev); the compose
    # worker runs with it enabled, and the drill exercises that path.
    jobs_enabled: bool = False
    jobs_stream: str = "br:jobs"
    jobs_max_attempts: int = 3
    jobs_heartbeat_ttl_seconds: int = 30
    # Aliyun Bailian (DashScope): one key for the OpenAI-compatible LLM endpoint and for
    # the batch speech model. Credentials only ever come from the environment.
    dashscope_api_key: str = ""
    # P3: Model Studio application calls. The app id is *not* a credential but it is
    # account-specific, so it lives here (env name only in .env.example) and the scene
    # binding row decides which app serves which scene.
    dashscope_app_id: str = ""
    dashscope_app_base_url: str = "https://dashscope.aliyuncs.com"
    xunfei_app_id: str = ""
    xunfei_access_key_id: str = ""
    xunfei_access_key_secret: str = ""

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
