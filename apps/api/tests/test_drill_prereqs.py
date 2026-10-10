"""M6-T8: the drill must fail loudly when it cannot run, and never silently "pass".

The full drill needs Docker and is executed by `scripts/kill_instance_drill.sh`; this test
pins the prerequisite semantics and the parts of the contract the evidence depends on.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import httpx
import pytest
from scripts.kill_instance_drill import post_answer, retry_after_seconds

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "kill_instance_drill.sh"
DRIVER = REPO_ROOT / "apps" / "api" / "scripts" / "kill_instance_drill.py"
SMOKE = REPO_ROOT / "scripts" / "compose_smoke.sh"
FAULT = REPO_ROOT / "scripts" / "fault_injection_drill.sh"
BASH = shutil.which("bash") or "/bin/bash"

# P35: the three drills that bring the stack up and seed the smoke model row.
DRILL_SCRIPTS = (SMOKE, SCRIPT, FAULT)

#: P45: buildx >= 0.37.2 enforces the bake entitlement consent gate even under
#: --progress=rawjson (GHSA-gwr2-q96m-6682). Compose builds through `buildx bake` and never
#: grants `network.host`, so a build that *requests* host networking is refused outright:
#: `additional privileges requested: pass "--allow=network.host"`. The stack's compose file
#: asks for it (WSL2 proxy), so every script that builds the stack must opt out of bake.
BAKE_OFF = "COMPOSE_BAKE=false"
BUILDING_SCRIPTS = (SMOKE, SCRIPT, FAULT)


@pytest.mark.parametrize("script", BUILDING_SCRIPTS, ids=lambda path: path.name)
def test_a_script_that_builds_the_stack_opts_out_of_bake(script: Path) -> None:
    """P45: nightly went red twice (2026-10-09/10) in the first build step -- the runner
    image bumped buildx 0.37.1 -> 0.37.2, which stopped skipping the entitlement consent
    check under --progress=rawjson. compose.yaml requests network.host for the local proxy,
    and Compose's bake path only ever passes --allow fs.read / security.insecure, so the
    build is refused before it starts.

    COMPOSE_BAKE=false restores the classic path, which hands the declared entitlements
    straight to the builder. Pin it per script: a new drill that builds the stack without
    the opt-out would otherwise only fail on the nightly schedule."""
    # Match a live directive, not the string: the explanatory comment above it names the
    # variable too, so a substring check would pass with the export deleted (measured --
    # the first cut of this guard stayed green against exactly that mutation).
    live = [
        line.strip()
        for line in script.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]

    assert f"export {BAKE_OFF}" in live, (
        f"{script.name} builds the stack but never exports {BAKE_OFF} "
        f"(a comment mentioning it does not count)"
    )


MIGRATE_RUN = re.compile(r"docker compose run\b[^\n]*\bmigrate\b")
#: httpx needs an absolute URL; the drill builds these from --base at runtime.
URL = "http://drill.test/api/v1/interview/sessions/s1/answers"


def run_drill(*, path: str, script: Path = SCRIPT) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PATH"] = path
    return subprocess.run(  # noqa: S603 - fixed argv, this is the test harness
        [BASH, str(script)], capture_output=True, text=True, env=env, timeout=60, check=False
    )


def test_wrapper_scales_to_two_instances_and_calls_the_driver() -> None:
    body = SCRIPT.read_text(encoding="utf-8")

    assert "--scale api=2" in body
    assert "scripts.kill_instance_drill" in body
    assert "--wait" in body


@pytest.mark.parametrize("script", DRILL_SCRIPTS, ids=lambda path: path.name)
def test_missing_docker_exits_two_with_an_explanation(script: Path) -> None:
    # An empty PATH means neither docker nor uv exists: the drill must say so and exit 2.
    # A drill that silently "passes" is worse than no drill. compose_smoke.sh had no
    # guard at all (P35 follow-up): it died inside `docker compose config` with a bare 127.
    result = run_drill(path="/nonexistent", script=script)

    assert result.returncode == 2, result.stdout + result.stderr
    assert "docker" in (result.stdout + result.stderr)


def test_scripts_find_uv_even_when_the_shell_path_lacks_it() -> None:
    # A fresh root shell has no ~/.local/bin on PATH, which made the drill refuse to run
    # (M6 acceptance finding): both scripts must look for uv themselves and say how to fix
    # PATH when they cannot find it at all.
    for script in (SCRIPT, SMOKE):
        body = script.read_text(encoding="utf-8")
        assert ".local/bin/uv" in body, script.name
        assert "export PATH" in body, script.name


def run_fault_script(*args: str, path: str | None = None) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    if path is not None:
        env["PATH"] = path
    return subprocess.run(  # noqa: S603 - fixed argv, this is the test harness
        [BASH, str(FAULT), *args], capture_output=True, text=True, env=env, timeout=60, check=False
    )


def test_help_lists_the_sentinel_switch_before_any_prerequisite_check() -> None:
    """P5：--help 必须在 docker/uv 检查之前返回——没 docker 的机器上也要能看懂新开关。"""
    result = run_fault_script("--help", path="/nonexistent")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "--sentinel" in result.stdout
    assert "BR_REDIS_SENTINELS" in result.stdout
    # 恢复拓扑的坑要写在用法里，别只活在某个人的记忆里。
    assert "down -v" in result.stdout


def test_an_unknown_option_is_refused_with_the_usage() -> None:
    result = run_fault_script("--nope", path="/nonexistent")

    assert result.returncode == 2
    assert "--sentinel" in (result.stdout + result.stderr)


def test_sentinel_mode_wires_the_app_to_the_sentinels_and_restores_on_exit() -> None:
    """P5：应用走哨兵必须显式 export 两个变量；恢复动作挂 EXIT（finally 语义）。"""
    body = FAULT.read_text(encoding="utf-8")

    assert 'BR_REDIS_SENTINELS="redis://redis-sentinel-1:26379' in body
    assert "BR_REDIS_MASTER_NAME" in body
    assert "--profile drill" in body
    assert "--scenario redis-failover" in body and "--auto" in body
    assert "trap restore EXIT" in body
    assert "sentinel reset" in body


def test_drill_probe_uses_a_short_window_and_reports_attempts() -> None:
    # The first post-kill request can be held by the dead upstream; with a 5s client
    # timeout that wait was reported as "kill -> recovery 5.4s", which measured the probe
    # rather than nginx. Poll with a short timeout and publish the attempt count.
    body = DRIVER.read_text(encoding="utf-8")

    assert "PROBE_TIMEOUT_SECONDS" in body
    assert "attempts" in body
    assert "1.0" in body


@pytest.mark.parametrize("script", DRILL_SCRIPTS, ids=lambda path: path.name)
def test_drills_migrate_the_schema_before_seeding_the_smoke_model(script: Path) -> None:
    # P35: the seed used to run before the one-shot migrate job. That passes on a warm
    # local volume (the table is already there from earlier runs) and fails on every cold
    # one — which is why nightly was red five nights running with
    # `relation "ai_models" does not exist`. Pin the order, not the wording.
    body = script.read_text(encoding="utf-8")

    postgres_at = body.index("up -d --wait postgres redis")
    migrate = MIGRATE_RUN.search(body)
    seed_at = body.index("INSERT INTO ai_models")

    assert migrate is not None, f"{script.name} seeds ai_models without running migrate"
    assert postgres_at < migrate.start() < seed_at, script.name


@pytest.mark.parametrize(
    ("header", "expected"),
    [(None, 1.0), ("2", 2.0), ("0", 0.0), ("-5", 0.0), ("Wed, 21 Oct 2015 07:28:00 GMT", 1.0)],
)
def test_retry_after_seconds_parses_the_header_with_a_fallback(
    header: str | None, expected: float
) -> None:
    headers = {} if header is None else {"retry-after": header}
    assert retry_after_seconds(httpx.Response(429, headers=headers)) == expected


async def test_post_answer_honours_retry_after_then_succeeds() -> None:
    # P36: the answer bucket is 2 rps (P1-B calibration) and the drill fires answers as fast
    # as the fake vendor replies, so a 429 is expected. Retrying the same idempotent
    # request_id is the fix; crashing on `.json()["next_action"]` was the bug.
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) < 3:
            return httpx.Response(429, headers={"retry-after": "0"})
        return httpx.Response(201, json={"next_action": "finished"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        response = await post_answer(client, URL, {"request_id": "drill-2"})

    assert response.status_code == 201
    assert len(calls) == 3
    assert response.json()["next_action"] == "finished"


async def test_post_answer_raises_with_the_body_instead_of_a_keyerror() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(409, json={"detail": "session is not accepting answers"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(RuntimeError) as excinfo:
            await post_answer(client, URL, {"request_id": "drill-2"})

    assert "409" in str(excinfo.value)
    assert "not accepting answers" in str(excinfo.value)


def test_driver_never_lets_a_proxy_swallow_the_loopback_drill() -> None:
    body = DRIVER.read_text(encoding="utf-8")

    assert "trust_env=False" in body
    assert "x-instance-id" in body
    assert "summary_pending" in body  # the worker's queued job is part of the drill
    assert "replayed" in body  # a retry must not be scored twice
