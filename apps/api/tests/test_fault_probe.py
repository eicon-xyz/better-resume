"""V6: the soak/fault probe must classify outcomes honestly and refuse to fake a run.

The probe talks to the stack through nginx and injects faults with docker; these tests cover
the pure parts (classification, wave aggregation) and the "no docker" contract of the shell
wrapper, so the script's logic is exercised without a running stack.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import httpx
import pytest
from scripts import fault_probe

REPO_ROOT = Path(__file__).resolve().parents[3]
WRAPPER = REPO_ROOT / "scripts" / "fault_injection_drill.sh"
BASH = shutil.which("bash") or "/bin/bash"


def test_classify_response_covers_the_whole_taxonomy() -> None:
    assert fault_probe.classify_response(status=200) == "ok"
    assert fault_probe.classify_response(status=201) == "ok"
    assert fault_probe.classify_response(status=429) == "rate_limited"
    assert fault_probe.classify_response(status=503) == "server_error"
    assert fault_probe.classify_response(status=500) == "server_error"
    assert fault_probe.classify_response(exc=httpx.ConnectTimeout("x")) == "timeout"
    assert fault_probe.classify_response(exc=httpx.ReadTimeout("x")) == "timeout"
    assert fault_probe.classify_response(exc=httpx.ConnectError("x")) == "transport"
    assert fault_probe.classify_response(exc=ValueError("x")) == "unexpected"


def test_parse_replica_link_reads_master_link_status() -> None:
    """P1-D: the failover drill must decide "is the replica in sync?" from real INFO output."""
    assert (
        fault_probe.parse_replica_link("# Replication\r\nrole:slave\r\nmaster_link_status:up\r\n")
        == "up"
    )
    assert fault_probe.parse_replica_link("role:slave\nmaster_link_status:down\n") == "down"
    assert fault_probe.parse_replica_link("role:master\nconnected_slaves:0\n") == "unknown"


def test_summarise_waves_computes_growth_from_first_to_last() -> None:
    waves = [
        {"ok": 10, "timeout": 0, "server_error": 0, "redis_keys": 100, "pg_connections": 5},
        {"ok": 8, "timeout": 2, "server_error": 0, "redis_keys": 140, "pg_connections": 6},
        {"ok": 9, "timeout": 0, "server_error": 1, "redis_keys": 160, "pg_connections": 6},
    ]

    summary = fault_probe.summarise_waves(waves)

    assert summary["waves"] == 3
    assert summary["ok"] == 27
    assert summary["failures"] == 3
    assert summary["error_rate"] == pytest.approx(3 / 30)
    assert summary["redis_keys_growth"] == 60
    assert summary["pg_connections_growth"] == 1
    assert summary["kinds"] == {"ok": 27, "timeout": 2, "server_error": 1}


def test_summarise_waves_handles_an_empty_run() -> None:
    summary = fault_probe.summarise_waves([])

    assert summary["waves"] == 0
    assert summary["error_rate"] == 0.0
    assert summary["redis_keys_growth"] == 0


def test_probe_never_lets_a_proxy_swallow_the_loopback_traffic() -> None:
    body = Path(fault_probe.__file__).read_text(encoding="utf-8")

    assert "trust_env=False" in body
    assert "PROBE_TIMEOUT_SECONDS" in body


def run_wrapper(*, path: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PATH"] = path
    return subprocess.run(  # noqa: S603 - fixed argv, this is the test harness
        [BASH, str(WRAPPER)], capture_output=True, text=True, env=env, timeout=60, check=False
    )


def test_wrapper_scales_the_stack_and_runs_every_experiment() -> None:
    body = WRAPPER.read_text(encoding="utf-8")

    assert "--scale api=2" in body
    assert "redis-pause" in body and "redis-restart" in body
    assert "worker-crash" in body and "soak" in body


def test_wrapper_without_docker_exits_two_with_an_explanation() -> None:
    result = run_wrapper(path="/nonexistent")

    assert result.returncode == 2, result.stdout + result.stderr
    assert "docker" in (result.stdout + result.stderr)


async def test_wait_until_the_stack_is_usable_rides_out_a_settling_cache() -> None:
    """P38: right after the failover experiment restores the master, the scene/registry caches
    answer 503 for a while. The reclaim experiment must wait that out instead of dying on it."""
    scene_calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if "/scenes/" not in request.url.path:
            return httpx.Response(200, json={"user_id": "u1"})
        scene_calls.append(request.url.path)
        if len(scene_calls) <= 2:
            return httpx.Response(503, json={"detail": "cache warming", "kind": "unavailable"})
        return httpx.Response(200, json={})

    async with httpx.AsyncClient(
        base_url="http://probe.test", transport=httpx.MockTransport(handler)
    ) as client:
        await fault_probe.wait_until_the_stack_is_usable(
            client, model="smoke-fake", budget_seconds=10.0, delay=0.0
        )

    assert len(scene_calls) > 2, "the gate must retry, not give up on the first 503"


async def test_wait_until_the_stack_is_usable_still_fails_when_it_never_recovers() -> None:
    """A gate that waits forever would hide a real outage; it must still give up loudly."""

    def handler(request: httpx.Request) -> httpx.Response:
        if "/scenes/" not in request.url.path:
            return httpx.Response(200, json={"user_id": "u1"})
        return httpx.Response(503, json={"detail": "redis unavailable"})

    async with httpx.AsyncClient(
        base_url="http://probe.test", transport=httpx.MockTransport(handler)
    ) as client:
        with pytest.raises(RuntimeError) as excinfo:
            await fault_probe.wait_until_the_stack_is_usable(
                client, model="smoke-fake", budget_seconds=0.0, delay=0.0
            )

    assert "503" in str(excinfo.value)


async def test_login_with_retry_survives_a_stale_connection() -> None:
    """P37: worker-crash runs straight after the failover experiment restores the master; its
    first login came back 503 and killed the whole drill. 503 is P17's "dependency is down",
    so it is retried — the soak already did this, worker-crash did not."""
    statuses = [503, 503, 200]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(statuses.pop(0), json={"user_id": "u1"})

    async with httpx.AsyncClient(
        base_url="http://probe.test", transport=httpx.MockTransport(handler)
    ) as client:
        response = await fault_probe.login_with_retry(client, delay=0.0)

    assert response.status_code == 200
    assert statuses == []


async def test_login_with_retry_still_raises_when_the_dependency_stays_down() -> None:
    """The retry must not turn a dead dependency into a silent pass."""
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(503, json={"detail": "redis unavailable"})

    async with httpx.AsyncClient(
        base_url="http://probe.test", transport=httpx.MockTransport(handler)
    ) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await fault_probe.login_with_retry(client, attempts=3, delay=0.0)

    assert len(calls) == 3
