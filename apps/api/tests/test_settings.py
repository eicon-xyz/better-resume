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
