"""P2-T1: scripts/verify.sh is the single entry point for every verification layer.

CI and local must call the same commands (M6 P16: "local green, CI red" happened because the
two drifted). This file pins the script's own contract: the layer list and dry-run behaviour.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
VERIFY = REPO_ROOT / "scripts" / "verify.sh"
BASH = shutil.which("bash") or "/bin/bash"


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


def _list_layers() -> list[str]:
    """The layer headers --list actually prints (coverage: etc.), in order."""
    return [
        line.strip().rstrip(":")
        for line in run_verify("--list").stdout.splitlines()
        if line and not line[0].isspace() and line.strip().endswith(":")
    ]


def test_list_exposes_every_layer() -> None:
    """Every layer the script accepts needs its own header in --list. The first cut of this test
    only asked whether the substring appeared anywhere in the output, so a layer could vanish
    from the map with nothing noticing -- and coverage did."""
    result = run_verify("--list")
    assert result.returncode == 0
    layers = _list_layers()
    for layer in (
        "unit",
        "contract",
        "coverage",
        "deploy",
        "fault",
        "soak",
        "real",
        "scripts",
        "all",
    ):
        assert layer in layers, f"missing layer header in --list: {layer} (got {layers})"
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


def _dry_run_command_list(
    layer: str, scope: str = "all", env: dict[str, str] | None = None
) -> list[str]:
    result = run_verify("--layer", layer, "--scope", scope, "--dry-run", env=env)
    assert result.returncode == 0, result.stderr
    return [
        line.strip()[2:] for line in result.stdout.splitlines() if line.strip().startswith("$ ")
    ]


def _dry_run_commands(
    layer: str, scope: str = "all", env: dict[str, str] | None = None
) -> set[str]:
    return set(_dry_run_command_list(layer, scope, env))


def _list_map() -> dict[str, list[str]]:
    """The layer map --list prints: layer -> its advertised command lines.

    Only the tagged lines (api:/web:/all:) are commands; untagged lines are prose the map is
    allowed to carry (a note about the manual strict gate, the all-layer label)."""
    mapped: dict[str, list[str]] = {}
    current: str | None = None
    for line in run_verify("--list").stdout.splitlines():
        if line and not line[0].isspace() and line.strip().endswith(":"):
            current = line.strip().rstrip(":")
            mapped[current] = []
            continue
        match = re.match(r"^\s+(api|web|all): (.+)$", line)
        if match and current:
            mapped[current].append(match.group(2).strip())
    return mapped


def _synthetic_env_file(tmp_path: Path) -> str:
    """Credentials that satisfy the real layer's preflight and can never reach a vendor."""
    env_file = tmp_path / "synthetic.env"
    env_file.write_text(
        "BR_DASHSCOPE_API_KEY=sk-test\n"
        "BR_MEDIA__ASR_URL=https://example.invalid/asr\n"
        "BR_MEDIA__ASR_WS_URL=wss://example.invalid/ws\n",
        encoding="utf-8",
    )
    return str(env_file)


@pytest.mark.parametrize(
    "layer", ["unit", "contract", "coverage", "deploy", "fault", "soak", "real", "scripts"]
)
def test_the_list_map_names_the_commands_each_layer_really_runs(layer: str, tmp_path: Path) -> None:
    """P44: the map in --list is a second, hand-written copy of the layer plan, and copies
    drift. Measured 2026-10-09: 5 of 21 advertised lines disagreed with the real expansion
    (unit advertised a bare pytest while the layer runs one with --cov; coverage advertised a
    prose placeholder; soak dropped the mkdir/--base/absolute --json; scripts dropped the
    trailing echo), and the real layer was not in the map at all.

    A substring check cannot see any of that -- it asserts the map is roughly right. Only
    equality can, so this pins the map to the expansion it describes."""
    env = {"VERIFY_ENV_FILE": _synthetic_env_file(tmp_path)} if layer == "real" else None
    real = _dry_run_command_list(layer, env=env)
    assert real, f"--layer {layer} expands to no commands"
    # Lists, not sets: verbatim means order and duplicates count too. A set comparison would
    # forgive a map that prints the right commands in the wrong order.
    advertised = _list_map()[layer]
    assert advertised == real, (
        f"--list advertises commands that layer {layer} does not run: "
        f"{sorted(set(advertised) - set(real))}; and hides ones it does: "
        f"{sorted(set(real) - set(advertised))}; or prints them in a different order"
    )


def test_the_coverage_floor_runs_after_the_pytest_that_writes_its_data() -> None:
    """add_coverage judges coverage-api.json, which add_api_unit writes -- an implicit coupling
    the builder's own comment admits. Pin the order: a floor check that runs first reads the
    previous run's file (or none) and reports a confident verdict about stale data."""
    commands = _dry_run_command_list("all")
    writer = next(i for i, c in enumerate(commands) if "--cov-report=json:coverage-api.json" in c)
    judge = next(i for i, c in enumerate(commands) if "check_coverage_floors.py" in c)
    assert writer < judge, commands


def test_coverage_layer_respects_the_scope_flag() -> None:
    """--scope picks which half of the stack to verify (CI runs --scope api and --scope web).
    coverage ignored it: --scope web still ran the whole API pytest and the floor check, so the
    flag silently did nothing for that layer while unit and contract honoured it."""
    assert _dry_run_commands("coverage", scope="web") == set()
    api_commands = _dry_run_commands("coverage", scope="api")
    assert api_commands == _dry_run_commands("coverage", scope="all")
    assert any("check_coverage_floors.py" in c for c in api_commands)


def test_the_list_map_shows_the_full_plan_even_when_a_scope_is_given() -> None:
    """--list is the map of the plan, so it must not silently hide the half a scope excludes:
    a reader asking "what does all run?" would otherwise get a map shaped by an unrelated flag.
    The map and a scoped expansion therefore differ by construction -- deliberate, and pinned
    here rather than left for someone to discover."""
    scoped = run_verify("--list", "--scope", "api").stdout
    full = run_verify("--list").stdout
    assert scoped == full
    assert "vitest" in full  # the web half stays on the map under --scope api


def test_a_scope_with_nothing_to_run_says_so() -> None:
    """Silence would read as "the web coverage was verified" -- the layer must admit it ran
    nothing rather than exit 0 quietly."""
    result = run_verify("--layer", "coverage", "--scope", "web", "--dry-run")
    assert result.returncode == 0
    assert "nothing to run" in result.stdout


def test_all_layer_actually_runs_unit_contract_coverage_and_scripts() -> None:
    """P31 + P8-retro: --list and AGENTS.md call "all" the local closure; pin the real expansion
    instead of trusting the label. The contract layer silently went missing once (a formatting
    failure stayed invisible locally until CI), and the coverage floors turned out to sit outside
    "all" the same way — a broken floor would have been locally green and CI red."""
    all_commands = _dry_run_commands("all")
    for layer in ("unit", "contract", "coverage", "scripts"):
        missing = _dry_run_commands(layer) - all_commands
        assert not missing, f"--layer all skips the {layer} layer: {sorted(missing)}"


def test_the_list_map_does_not_advertise_the_manual_strict_gate() -> None:
    """D22 + P31: --strict (byte-level citation checking) is a manual close-out step, while the
    scripts layer deliberately runs --structural. The hand-written map in --list said --strict,
    so a reader would think CI checks citations byte-level — the label/expansion drift again."""
    listing = run_verify("--list").stdout
    # Only command lines matter: a note *about* the strict gate is fine, a command that runs it
    # as part of a layer is the drift this pins.
    commands = [
        line.strip()
        for line in listing.splitlines()
        if line.strip().startswith(("api:", "web:", "all:"))
    ]

    offenders = [line for line in commands if "--strict" in line]
    assert not offenders, f"the layer map advertises the manual strict gate: {offenders}"
    assert any("verify_audit_evidence.py --structural" in line for line in commands), commands


def test_the_all_label_names_every_layer_it_runs() -> None:
    """The label is what a human (and AGENTS.md) reads before trusting the run (P31 again)."""
    listing = run_verify("--list").stdout
    label = next(line for line in listing.splitlines() if line.strip().startswith("= "))

    for layer in ("unit", "contract", "coverage", "scripts"):
        assert layer in label, f"--list advertises all without {layer}: {label!r}"


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
    # CI runs the drift-stable level; --strict is the manual close-out gate (D22).
    structural = [c for c in commands if "verify_audit_evidence.py --structural" in c]
    assert structural, sorted(commands)


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


def _run_audit_checker(*args: str, units: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed argv, this is the test harness
        [sys.executable, str(AUDIT_CHECKER), *args, "--units", str(units)],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=REPO_ROOT,
    )


def _write_drifted_unit(units: Path) -> None:
    """Structurally valid, byte-level stale: what a code refactor does to an audit citation."""
    (units / "drift.json").write_text(
        json.dumps(
            {
                "unit": "drift",
                "issues": [
                    {
                        "id": "drift-01",
                        "severity": "中",
                        "dim": "R11 重复",
                        "title": "the cited range exists but no longer holds the quoted line",
                        "where": ["apps/api/src/better_resume/redis_client.py:1-2"],
                        "evidence": "1: import redis.asyncio as aioredis  # not in 1-2 after drift",
                        "why": "line drift moves citations without changing behaviour",
                        "fix": "re-anchor at close-out",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def test_structural_level_tolerates_line_drift_that_strict_rejects(tmp_path: Path) -> None:
    """D22: CI must survive a pure line shift; the close-out gate must still catch it.

    A workspace refactor that only moves lines must not turn CI red, so the scripts layer runs
    the structural level. The byte-level check stays a manual close-out step. This pins both
    halves of that split: without it, someone would "fix" CI by weakening the strict gate too.
    """
    units = tmp_path / "units"
    units.mkdir()
    _write_drifted_unit(units)

    structural = _run_audit_checker("--structural", units=units)
    assert structural.returncode == 0, structural.stdout
    assert "structure ok" in structural.stdout

    strict = _run_audit_checker("--strict", units=units)
    assert strict.returncode == 1, strict.stdout
    assert "unverifiable: 1" in strict.stdout


def test_structural_level_rejects_rot_that_is_not_drift(tmp_path: Path) -> None:
    """The CI level still has teeth: missing fields and citations past EOF must fail it."""
    units = tmp_path / "units"
    units.mkdir()
    (units / "rot.json").write_text(
        json.dumps(
            {
                "unit": "rot",
                "issues": [
                    {
                        "id": "rot-01",
                        "severity": "高",
                        "dim": "R11 重复",
                        "title": "missing why, and a range past the end of the file",
                        "where": ["apps/api/src/better_resume/redis_client.py:9000-9001"],
                        "evidence": "1: irrelevant",
                        "fix": "none",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    result = _run_audit_checker("--structural", units=units)
    assert result.returncode == 1, result.stdout
    assert "missing why" in result.stdout
    assert "outside 1.." in result.stdout
