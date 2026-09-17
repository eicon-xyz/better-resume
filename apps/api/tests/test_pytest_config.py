"""P2-T2: the pytest layer markers (unit/docker/real) are declared and the default run
excludes the heavy layers. This pins the config so a stray marker or a missing default
filter cannot silently bring the compose/real-machine layers into every test run."""

from __future__ import annotations

import tomllib
from pathlib import Path

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def _pytest_options() -> dict:
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    return data["tool"]["pytest"]["ini_options"]


def test_strict_markers_and_default_exclusion_are_configured() -> None:
    options = _pytest_options()
    addopts = options["addopts"]
    assert "--strict-markers" in addopts, "unknown markers must fail, not warn"
    assert "not docker and not real" in addopts, (
        "the default run must exclude the compose/real-machine layers"
    )


def test_docker_and_real_markers_are_registered() -> None:
    markers = _pytest_options().get("markers", [])
    joined = "\n".join(markers)
    assert "docker:" in joined, "compose-stack tests need the docker marker"
    assert "real:" in joined, "vendor-cost tests need the real marker"
