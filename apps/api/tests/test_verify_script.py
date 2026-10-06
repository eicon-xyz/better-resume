"""P2-T1: scripts/verify.sh is the single entry point for every verification layer.

CI and local must call the same commands (M6 P16: "local green, CI red" happened because the
two drifted). This file pins the script's own contract: the layer list and dry-run behaviour.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
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


def _dry_run_commands(layer: str) -> set[str]:
    result = run_verify("--layer", layer, "--dry-run")
    assert result.returncode == 0, result.stderr
    return {
        line.strip()[2:] for line in result.stdout.splitlines() if line.strip().startswith("$ ")
    }


def test_all_layer_actually_runs_unit_contract_and_scripts() -> None:
    """P31: --list and AGENTS.md advertise "all = unit + contract + scripts"; pin the real
    expansion instead of trusting the label. The contract layer silently went missing once,
    which is exactly how a formatting failure stayed invisible locally until CI."""
    all_commands = _dry_run_commands("all")
    for layer in ("unit", "contract", "scripts"):
        missing = _dry_run_commands(layer) - all_commands
        assert not missing, f"--layer all skips the {layer} layer: {sorted(missing)}"


def test_soak_layer_writes_its_evidence_where_the_workflow_collects_it() -> None:
    """P39: the soak layer runs with cwd=apps/api, so `--json var/evidence/soak-60m.json`
    pointed at apps/api/var/evidence/ (which does not exist). The 60-minute soak finished,
    passed, and then died writing its evidence — an hour of CI time lost to a path.
    """
    commands = _dry_run_commands("soak")
    line = next(c for c in commands if "fault_probe soak" in c)
    raw = line.split("--json", 1)[1].strip()

    # Absolute (not relative to apps/api) AND quoted — the checkout path can contain spaces.
    assert raw.startswith('"') and raw.endswith('"'), f"--json must be quoted: {raw!r}"
    json_path = raw.strip('"')
    assert json_path.startswith("/"), f"--json must be absolute, got {json_path!r}"
    assert json_path.endswith("var/evidence/soak-60m.json"), json_path
    assert "mkdir -p var/evidence" in line


def test_scripts_layer_checks_the_scripts_themselves() -> None:
    """Retro 2026-10-06: the layer ran the drill scripts' pytest but never checked the shell
    scripts they live beside, so a proof script that unconditionally exited 0 shipped through
    a green CI. The layer now sweeps shell/python syntax and gates the evidence checker."""
    commands = _dry_run_commands("scripts")
    loop = [c for c in commands if "bash -n" in c]
    assert loop, sorted(commands)
    # `bash -n a.sh b.sh` only checks the first file; the loop must cover every one.
    assert any("for f in scripts/*.sh" in c and "bash -n" in c for c in loop), sorted(commands)
    assert any("check_scripts.py" in command for command in commands), sorted(commands)
    strict = [c for c in commands if "verify_audit_evidence.py --strict" in c]
    assert strict, sorted(commands)


VERIFY_MUTATION = REPO_ROOT / "scripts" / "verify_mutation.sh"
CONTRACT_TEST = "tests/ai_resilience/test_ratelimit_equivalence.py"
CONTRACT_SRC = "apps/api/src/better_resume/ai_resilience/redis_buckets.py"


def _run_mutation_proof(test_cmd: str, find: str, replace: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed argv, this is the test harness
        [
            BASH,
            str(VERIFY_MUTATION),
            "--test",
            test_cmd,
            "--file",
            CONTRACT_SRC,
            "--find",
            find,
            "--replace",
            replace,
        ],
        capture_output=True,
        text=True,
        timeout=300,
        cwd=REPO_ROOT,
    )


def test_mutation_proof_passes_only_when_the_test_catches_the_mutation() -> None:
    """The equivalence test must go red when the Lua refill drifts (ai-02). If this fails,
    either the test lost its teeth or the proof script lost its exit code."""
    pytest_cmd = f"cd '{REPO_ROOT}/apps/api' && ./.venv/bin/python -m pytest {CONTRACT_TEST} -q"
    result = _run_mutation_proof(
        pytest_cmd, "tokens = tokens + elapsed / 1000 * rate", "tokens = tokens + elapsed * rate"
    )
    assert result.returncode == 0, (result.stdout[-2000:], result.stderr[-500:])
    assert "PASS: baseline green -> mutation red -> restored green" in result.stdout


def test_mutation_proof_refuses_an_anchor_that_is_gone() -> None:
    """A proof whose anchor no longer exists must fail loudly (exit 2), never pass by default."""
    result = _run_mutation_proof("true", "AN ANCHOR THAT IS NOT IN THE FILE", "whatever")
    assert result.returncode == 2
    assert "anchor not present" in result.stderr


AUDIT_UNITS = REPO_ROOT / "docs" / "audit" / "units"
AUDIT_CHECKER = REPO_ROOT / "scripts" / "verify_audit_evidence.py"


def test_every_audit_citation_is_corroborated_by_its_evidence() -> None:
    """Docs audit gate: each issue's where-citations must be backed by the evidence block
    quoted in the issue. Runs strict, so a partial citation counts as a failure."""
    if not AUDIT_UNITS.is_dir():
        return
    result = subprocess.run(  # noqa: S603 - fixed argv, this is the test harness
        [sys.executable, str(AUDIT_CHECKER), "--strict"],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stdout[-2000:]
    assert "unverifiable: 0" in result.stdout


def test_audit_checker_fails_loudly_on_a_bad_citation(tmp_path: Path) -> None:
    """Fail-loud half of the gate: a claim whose citation does not contain its own evidence
    must be reported. Guards against the checker quietly becoming a no-op."""
    units = tmp_path / "units"
    units.mkdir()
    (units / "bogus.json").write_text(
        json.dumps(
            {
                "unit": "bogus",
                "issues": [
                    {
                        "id": "bogus-01",
                        "severity": "高",
                        "dim": "R11 重复",
                        "title": "citation points somewhere the evidence is not",
                        "where": ["apps/api/src/better_resume/redis_client.py:1-2"],
                        "evidence": "42: THIS LINE IS NOT IN THE CITED WINDOW",
                        "why": "the checker must catch this",
                        "fix": "none",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    result = subprocess.run(  # noqa: S603 - fixed argv, this is the test harness
        [sys.executable, str(AUDIT_CHECKER), "--strict", "--units", str(units)],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 1, result.stdout
    assert "unverifiable: 1" in result.stdout
