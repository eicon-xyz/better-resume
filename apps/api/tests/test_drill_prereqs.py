"""M6-T8: the drill must fail loudly when it cannot run, and never silently "pass".

The full drill needs Docker and is executed by `scripts/kill_instance_drill.sh`; this test
pins the prerequisite semantics and the parts of the contract the evidence depends on.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "kill_instance_drill.sh"
DRIVER = REPO_ROOT / "apps" / "api" / "scripts" / "kill_instance_drill.py"
BASH = shutil.which("bash") or "/bin/bash"


def run_drill(*, path: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PATH"] = path
    return subprocess.run(  # noqa: S603 - fixed argv, this is the test harness
        [BASH, str(SCRIPT)], capture_output=True, text=True, env=env, timeout=60, check=False
    )


def test_wrapper_scales_to_two_instances_and_calls_the_driver() -> None:
    body = SCRIPT.read_text(encoding="utf-8")

    assert "--scale api=2" in body
    assert "scripts.kill_instance_drill" in body
    assert "--wait" in body


def test_missing_docker_exits_two_with_an_explanation() -> None:
    # An empty PATH means neither docker nor uv exists: the drill must say so and exit 2.
    # A drill that silently "passes" is worse than no drill.
    result = run_drill(path="/nonexistent")

    assert result.returncode == 2, result.stdout + result.stderr
    assert "docker" in (result.stdout + result.stderr)


def test_driver_never_lets_a_proxy_swallow_the_loopback_drill() -> None:
    body = DRIVER.read_text(encoding="utf-8")

    assert "trust_env=False" in body
    assert "x-instance-id" in body
    assert "summary_pending" in body  # the worker's queued job is part of the drill
    assert "replayed" in body  # a retry must not be scored twice
