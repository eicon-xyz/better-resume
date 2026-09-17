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
