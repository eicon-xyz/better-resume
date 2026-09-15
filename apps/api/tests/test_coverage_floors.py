"""P2-T6 round 2: per-module coverage floors for the deep modules.

Criterion (user decision + codebase-design vocabulary): a module gets a floor when it passes
the deletion test, has a small stable interface, and hides thick implementation. Shallow
modules (adapters/factories/route shells) deliberately get NO floor. The checker reads the
coverage JSON produced by the unit layer and refuses (exit 2) listing every violation.
A deep module MISSING from the coverage data is also a violation: a broken coverage run must
not silently pass the floors."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
CHECKER = API_ROOT / "scripts" / "check_coverage_floors.py"
DEEP = [
    "ai_resilience",
    "identity",
    "interview_engine",
    "jobs",
    "llm_gateway",
    "media",
    "resume_parser",
]
FLOOR = 90.0


def write(tmp_path: Path, overrides: dict[str, float] | None = None) -> Path:
    percents = dict.fromkeys(DEEP, 95.0)
    percents.update(overrides or {})
    files = {
        f"src/better_resume/{mod}/x.py": {
            "summary": {"covered_lines": int(pct), "num_statements": 100}
        }
        for mod, pct in percents.items()
    }
    path = tmp_path / "coverage-api.json"
    path.write_text(json.dumps({"files": files}), encoding="utf-8")
    return path


def run_checker(json_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed argv, this is the test harness
        [sys.executable, str(CHECKER), "--json", str(json_path)],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(API_ROOT),
    )


def test_floors_pass_when_every_deep_module_is_above(tmp_path: Path) -> None:
    result = run_checker(write(tmp_path))
    assert result.returncode == 0, result.stdout + result.stderr


def test_floors_fail_and_name_the_violating_module(tmp_path: Path) -> None:
    result = run_checker(write(tmp_path, {"media": 85.0}))
    assert result.returncode == 2
    assert "media" in result.stdout
    assert "85.0" in result.stdout


def test_floors_ignore_shallow_modules(tmp_path: Path) -> None:
    result = run_checker(write(tmp_path, {"worker.py": 50.0, "db": 40.0, "http": 60.0}))
    assert result.returncode == 0, result.stdout + result.stderr


def test_floors_fail_without_a_coverage_json(tmp_path: Path) -> None:
    result = run_checker(tmp_path / "missing.json")
    assert result.returncode == 2
    assert "coverage" in (result.stdout + result.stderr).lower()
