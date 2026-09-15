"""P2-T3: the heavy verification layers run on a schedule (public repo = free runners).

Plan A: nightly = deploy layer + fault drill with the quick soak; weekly = full fault layer
(20-minute soak) + the 60-minute vendor-free soak. Both accept workflow_dispatch, cap their
runtime, and upload whatever evidence the drills left behind."""

from __future__ import annotations

from pathlib import Path

WORKFLOWS = Path(__file__).resolve().parents[3] / ".github" / "workflows"


def test_nightly_runs_deploy_and_quick_fault_on_a_schedule() -> None:
    text = (WORKFLOWS / "nightly.yml").read_text(encoding="utf-8")
    assert "schedule:" in text and "cron:" in text
    assert "workflow_dispatch" in text
    assert "verify.sh --layer deploy" in text
    assert "fault_injection_drill.sh --quick" in text
    assert "upload-artifact" in text
    assert "timeout-minutes" in text


def test_weekly_runs_full_fault_and_the_sixty_minute_soak() -> None:
    text = (WORKFLOWS / "weekly-full.yml").read_text(encoding="utf-8")
    assert "schedule:" in text and "cron:" in text
    assert "workflow_dispatch" in text
    assert "verify.sh --layer fault" in text
    assert "verify.sh --layer soak" in text
    assert "upload-artifact" in text
    assert "timeout-minutes" in text


def test_nightly_and_weekly_run_on_different_days() -> None:
    nightly = (WORKFLOWS / "nightly.yml").read_text(encoding="utf-8")
    weekly = (WORKFLOWS / "weekly-full.yml").read_text(encoding="utf-8")
    nightly_cron = next(line for line in nightly.splitlines() if "cron:" in line)
    weekly_cron = next(line for line in weekly.splitlines() if "cron:" in line)
    assert nightly_cron.strip() != weekly_cron.strip()
