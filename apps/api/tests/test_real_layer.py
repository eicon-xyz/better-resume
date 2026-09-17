"""P2-T4: the real layer is a budget-guarded, credential-checked, stage-closure MANDATORY
suite. Its contract: list what it will do (dry-run), refuse without credentials, and refuse
to overspend the vendor call budget. It never fakes a run and never silently skips."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
VERIFY = REPO_ROOT / "scripts" / "verify.sh"
FIXTURE_AUDIO = REPO_ROOT / "data" / "audio" / "p1c-multi-sentence-16k.wav"
BASH = shutil.which("bash") or "/bin/bash"
UV = shutil.which("uv") or "/root/.local/bin/uv"


def run_verify(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    import os

    merged = dict(os.environ)
    if env:
        merged.update(env)
    return subprocess.run(  # noqa: S603 - fixed argv, this is the test harness
        [BASH, str(VERIFY), *args],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=REPO_ROOT,
        env=merged,
    )


def write_synthetic_env(tmp_path: Path) -> Path:
    """Credentials that satisfy the preflight and can never reach a vendor."""
    env_file = tmp_path / "synthetic.env"
    env_file.write_text(
        "BR_DASHSCOPE_API_KEY=sk-test\n"
        "BR_MEDIA__ASR_URL=https://example.invalid/asr\n"
        "BR_MEDIA__ASR_WS_URL=wss://example.invalid/ws\n",
        encoding="utf-8",
    )
    return env_file


def run_fixture_check(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed argv, this is the test harness
        [UV, "run", "python", "scripts/make_fixture_audio.py", "--check", "--file", str(path)],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=REPO_ROOT / "apps" / "api",
    )


def test_real_layer_dry_run_lists_steps_and_budget(tmp_path: Path) -> None:
    env_file = write_synthetic_env(tmp_path)
    result = run_verify("--layer", "real", "--dry-run", env={"VERIFY_ENV_FILE": str(env_file)})
    assert result.returncode == 0
    assert "real_model_smoke" in result.stdout
    assert "paraformer-rt-real" in result.stdout
    assert "budget=200" in result.stdout
    assert "est=" in result.stdout


def test_real_layer_refuses_without_credentials() -> None:
    result = run_verify(
        "--layer", "real", "--dry-run", env={"VERIFY_ENV_FILE": "/nonexistent/.env"}
    )
    assert result.returncode == 2
    assert "refusing" in result.stderr
    assert "BR_DASHSCOPE_API_KEY" in result.stderr


def test_real_layer_budget_guard_blocks_overspend(tmp_path: Path) -> None:
    spent = tmp_path / "real_calls_spent.txt"
    spent.write_text("9999\n", encoding="utf-8")
    result = run_verify("--layer", "real", "--dry-run", env={"VERIFY_EVIDENCE_DIR": str(tmp_path)})
    assert result.returncode == 2
    assert "would exceed the call budget" in result.stderr


def test_fixture_audio_check_refuses_a_missing_file(tmp_path: Path) -> None:
    """P32: data/ is gitignored (Q3 never commits the wav), so the fixture is legitimately
    absent in a clean checkout. The check must therefore be tested against bytes the test
    owns -- an assertion that the developer's local wav exists is not hermetic (it passed
    here and failed on CI)."""
    result = run_fixture_check(tmp_path / "absent.wav")
    assert result.returncode == 2
    assert "missing fixture" in (result.stdout + result.stderr)


def test_real_layer_refuses_when_the_fixture_audio_is_absent(tmp_path: Path) -> None:
    """P32: refuse before spending, not halfway through a paid run."""
    result = run_verify(
        "--layer",
        "real",
        env={
            "VERIFY_ENV_FILE": str(write_synthetic_env(tmp_path)),
            "VERIFY_EVIDENCE_DIR": str(tmp_path / "evidence"),
            "VERIFY_FIXTURE_AUDIO_DIR": str(tmp_path / "no-audio-here"),
        },
    )
    assert result.returncode == 2
    assert "fixture" in result.stderr
    assert "make_fixture_audio.py" in result.stderr


def test_real_layer_refuses_when_the_pinned_fixture_drifted(tmp_path: Path) -> None:
    """P32: present-but-wrong bytes are as blocking as absent bytes (drift guard)."""
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    for name in ("p1c-multi-sentence-16k.wav", "v3-sample-16k.wav"):
        (audio_dir / name).write_bytes(b"RIFF-not-the-pinned-bytes")
    result = run_verify(
        "--layer",
        "real",
        env={
            "VERIFY_ENV_FILE": str(write_synthetic_env(tmp_path)),
            "VERIFY_EVIDENCE_DIR": str(tmp_path / "evidence"),
            "VERIFY_FIXTURE_AUDIO_DIR": str(audio_dir),
        },
    )
    assert result.returncode == 2
    assert "PINNED_SHA256" in result.stderr


def test_fixture_audio_check_detects_a_foreign_file(tmp_path: Path) -> None:
    foreign = tmp_path / "foreign.wav"
    foreign.write_bytes(b"RIFF-fake-not-the-pinned-audio")
    result = subprocess.run(  # noqa: S603 - fixed argv, this is the test harness
        [UV, "run", "python", "scripts/make_fixture_audio.py", "--check", "--file", str(foreign)],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=REPO_ROOT / "apps" / "api",
    )
    assert result.returncode == 2
    assert "sha256" in (result.stdout + result.stderr).lower()
