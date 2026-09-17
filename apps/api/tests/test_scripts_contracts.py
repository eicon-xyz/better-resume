"""P2-T5: every scripts/*.py carries at least two regression contracts.

Universal contracts for all scripts (import isolation, argparse usability) plus
per-script refusal/sync contracts for the vendor and drift-check paths, so a script can
never silently fake a run or drift its generated artifacts."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

API_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = API_ROOT / "scripts"
REPO_ROOT = API_ROOT.parents[1]

ALL_SCRIPTS = sorted(p.name for p in SCRIPTS.glob("*.py") if p.name != "__init__.py")
ARGPARSE_SCRIPTS = [
    "adapter_smoke.py",
    "assembler_real_probe.py",
    "dashscope_app_probe.py",
    "deploy_probe.py",
    "extract_api_index.py",
    "fake_openai.py",
    "kill_instance_drill.py",
    "media_smoke.py",
]  # export_openapi.py has no argparse: its contracts are import + --check sync
ENTRY_GUARD_SCRIPTS = ["interview_smoke.py", "resilience_smoke.py", "v3_ws_probe.py"]


def run_script(
    script: str, *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    merged = dict(os.environ)
    merged["BR_ENVIRONMENT"] = merged.get("BR_ENVIRONMENT", "local")
    if env:
        # Environment variables beat the dotenv file in pydantic-settings, so a test can
        # force "no credentials" even on a machine whose .env has them (never spend in CI).
        merged.update(env)
    return subprocess.run(  # noqa: S603 - fixed argv, this is the test harness
        [sys.executable, "-m", f"scripts.{script[:-3]}", *args],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(API_ROOT),
        env=merged,
    )


@pytest.mark.parametrize("script", ALL_SCRIPTS)
def test_script_imports_cleanly_without_running(script: str) -> None:
    result = subprocess.run(  # noqa: S603 - fixed argv, this is the test harness
        [sys.executable, "-c", f"import scripts.{script[:-3]}"],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(API_ROOT),
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("script", ARGPARSE_SCRIPTS)
def test_script_help_exits_zero(script: str) -> None:
    result = run_script(script, "--help")
    assert result.returncode == 0, result.stderr
    assert "usage" in result.stdout.lower()


@pytest.mark.parametrize("script", ENTRY_GUARD_SCRIPTS)
def test_non_argparse_script_has_an_entry_guard(script: str) -> None:
    text = (SCRIPTS / script).read_text(encoding="utf-8")
    assert '__name__ == "__main__"' in text, f"{script} would execute on import"


def test_media_smoke_refuses_a_real_run_without_wav() -> None:
    result = run_script("media_smoke.py", "--qwen-asr-real")
    assert result.returncode == 2
    assert "--wav" in result.stderr


def test_dashscope_app_probe_refuses_without_credentials() -> None:
    result = run_script(
        "dashscope_app_probe.py",
        env={"BR_DASHSCOPE_APP_ID": "", "BR_DASHSCOPE_API_KEY": ""},
    )
    assert result.returncode == 2
    assert "BR_DASHSCOPE_APP_ID" in result.stderr


def test_dashscope_app_probe_dry_run_spends_nothing() -> None:
    result = run_script(
        "dashscope_app_probe.py",
        "--dry-run",
        env={"BR_DASHSCOPE_APP_ID": "app-test-1234", "BR_DASHSCOPE_API_KEY": "sk-test"},
    )
    assert result.returncode == 0, result.stderr
    assert "DRY RUN" in result.stdout
    assert "1 vendor call" in result.stdout


def test_export_openapi_check_reports_in_sync() -> None:
    result = run_script("export_openapi.py", "--check")
    assert result.returncode == 0, result.stdout + result.stderr


def test_extract_api_index_check_reports_in_sync() -> None:
    result = run_script("extract_api_index.py", "--check")
    assert result.returncode == 0, result.stdout + result.stderr


def test_v3_ws_probe_documents_the_realtime_mode() -> None:
    text = (SCRIPTS / "v3_ws_probe.py").read_text(encoding="utf-8")
    assert "--realtime" in text, "the paced incremental mode must stay discoverable"
