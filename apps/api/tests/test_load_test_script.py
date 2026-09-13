"""M6-T6: the load-test script itself is tested (small runs; performance is not asserted).

The script is loaded by path because it lives outside the package; everything it drives is
the real app (in-process ASGI transport), so these cases also serve as a smoke test of the
endpoints under concurrency.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("m6_load_test", SCRIPTS / "load_test.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def load_test() -> ModuleType:
    return load_module()


async def run_script(load_test: ModuleType, tmp_path: Path, *extra: str) -> dict:
    output = tmp_path / "summary.json"
    code = await load_test.main(
        [
            "--scenario",
            "mixed",
            "--concurrency",
            "2",
            "--duration",
            "1",
            "--fake-llm",
            *extra,
            "--json",
            str(output),
        ]
    )
    assert code == 0
    return json.loads(output.read_text(encoding="utf-8"))


async def test_tiny_run_reports_every_metric(load_test: ModuleType, tmp_path: Path) -> None:
    summary = await run_script(load_test, tmp_path, "--rate-limit-off")

    for field in (
        "requests",
        "rps",
        "p50_ms",
        "p95_ms",
        "p99_ms",
        "error_rate",
        "rate_limited",
        "sse_first_frame_p50_ms",
        "transport",
        "fake_llm",
    ):
        assert field in summary, field

    assert summary["requests"] > 0
    assert summary["p95_ms"] >= summary["p50_ms"] >= 0
    assert summary["transport"] == "in-process ASGI"
    assert summary["error_rate"] == 0.0
    assert summary["errors"] == {}


async def test_rate_limiter_is_visible_in_the_numbers(
    load_test: ModuleType, tmp_path: Path
) -> None:
    summary = await run_script(load_test, tmp_path)  # limiter ON (the default)

    assert summary["rate_limited"] > 0, "the read bucket should reject a hot loop"
    assert summary["rate_limit"] == "on"
    assert summary["error_rate"] == 0.0, "429s are expected outcomes, not errors"


async def test_fake_llm_keeps_the_run_offline(load_test: ModuleType, tmp_path: Path) -> None:
    summary = await run_script(load_test, tmp_path, "--rate-limit-off")

    assert summary["fake_llm"] is True
    assert summary["fake_llm_calls"] > 0


def test_summary_math_is_honest(load_test: ModuleType) -> None:
    recorder = load_test.Recorder()
    recorder.latencies = [0.001, 0.002, 0.003, 0.004] * 25
    recorder.ok = 90
    recorder.errors = {"503": 10}
    summary = recorder.summary(duration=10.0)

    assert summary["requests"] == 100
    assert summary["rps"] == 10.0
    assert summary["error_rate"] == 0.1
    assert summary["p50_ms"] <= summary["p95_ms"] <= summary["p99_ms"]
