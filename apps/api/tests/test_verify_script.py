"""P2-T1: scripts/verify.sh is the single entry point for every verification layer.

CI and local must call the same commands (M6 P16: "local green, CI red" happened because the
two drifted). This file pins the script's own contract: the layer list, dry-run behaviour,
and the refusal to run unknown or not-yet-implemented layers.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
VERIFY = REPO_ROOT / "scripts" / "verify.sh"


def run_verify(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(VERIFY), *args], capture_output=True, text=True, timeout=120, cwd=REPO_ROOT
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


def test_real_layer_refuses_until_t4_implements_it() -> None:
    """T4 will add the budget-guarded real-machine suite; until then the layer must refuse
    loudly (this repo never fakes a run)."""
    result = run_verify("--layer", "real", "--dry-run")
    assert result.returncode == 2
    assert "T4" in result.stderr or "not implemented" in result.stderr
