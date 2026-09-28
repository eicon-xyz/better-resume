from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from better_resume.settings import Settings

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_defaults_are_dev_friendly() -> None:
    settings = Settings(_env_file=None)

    assert settings.environment == "local"
    assert settings.log_level == "INFO"
    assert settings.session_ttl_seconds == 60 * 60 * 24 * 30
    assert settings.database_url.startswith("postgresql+asyncpg://")


def test_env_vars_override_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BR_LOG_LEVEL", "debug")
    monkeypatch.setenv("BR_SESSION_COOKIE_NAME", "session_from_env")

    settings = Settings(_env_file=None)

    assert settings.log_level == "DEBUG"
    assert settings.session_cookie_name == "session_from_env"


def test_sentinel_vars_default_to_the_single_url_shape() -> None:
    """P5：不配哨兵时行为与今天完全一致（单 URL）。"""
    settings = Settings(_env_file=None)

    assert settings.redis_sentinels == ""
    assert settings.redis_master_name == ""


def test_sentinel_vars_are_read_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BR_REDIS_SENTINELS", "redis://sentinel-a:26379,redis://sentinel-b:26379")
    monkeypatch.setenv("BR_REDIS_MASTER_NAME", "br-master")

    settings = Settings(_env_file=None)

    assert settings.redis_sentinels == "redis://sentinel-a:26379,redis://sentinel-b:26379"
    assert settings.redis_master_name == "br-master"


def test_half_configured_sentinel_is_rejected() -> None:
    """只配一半 = 静默退回单 URL，切换时没人救得回来：启动即报错，并点名变量。"""
    with pytest.raises(ValidationError, match="BR_REDIS_MASTER_NAME"):
        Settings(_env_file=None, redis_sentinels="redis://sentinel-a:26379")

    with pytest.raises(ValidationError, match="BR_REDIS_SENTINELS"):
        Settings(_env_file=None, redis_master_name="br-master")


def test_invalid_database_url_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_url="mysql://user@localhost/db")


def test_invalid_log_level_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, log_level="LOUD")


def test_env_example_covers_settings_fields() -> None:
    """Contract: every BR_* key in .env.example maps to a real Settings field."""
    lines = (REPO_ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    keys = [
        line.split("=", 1)[0].strip() for line in lines if "=" in line and not line.startswith("#")
    ]

    br_keys = [key for key in keys if key.startswith("BR_")]
    assert br_keys, "expected BR_* keys in .env.example"

    for key in br_keys:
        assert key[3:].lower() in Settings.model_fields, f"{key} has no matching Settings field"
