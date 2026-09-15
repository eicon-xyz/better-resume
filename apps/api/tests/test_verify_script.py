"""P2-T1: scripts/verify.sh is the single entry point for every verification layer.

CI and local must call the same commands (M6 P16: "local green, CI red" happened because the
two drifted). This file pins the script's own contract: the layer list and dry-run behaviour.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
VERIFY = REPO_ROOT / "scripts" / "verify.sh"
BASH = shutil.which("bash") or "/bin/bash"


def run_verify(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed argv, this is the test harness
        [BASH, str(VERIFY), *args], capture_output=True, text=True, timeout=120, cwd=REPO_ROOT
    )


def test_list_exposes_every_layer() -> None:
    result = run_verify("--list")
    assert result.returncode == 0
    for layer in ("unit", "contract", "deploy", "fault", "soak", "real", "scripts", "all"):
        assert layer in result.stdout, f"missing layer in --list: {layer}"
    assert "pytest" in result.stdout and "vitest" in result.stdout


def test_dry_run_prints_unit_commands_without_running_them() -> None:
    result = run_verify("--layer", "unit", "--dry-run")
    assert result.returncode == 0
    assert "pytest" in result.stdout
    assert "vitest" in result.stdout
    # A dry run prints commands, never outcomes.
    assert "passed" not in result.stdout


def test_unknown_layer_refuses_to_run() -> None:
    result = run_verify("--layer", "bogus")
    assert result.returncode == 2
    assert "bogus" in result.stderr
