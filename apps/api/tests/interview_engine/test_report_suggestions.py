"""T5/rubric: long model-written missing points must not blow up the suggestions."""

from __future__ import annotations

from better_resume.interview_engine.report_service import shorten_point


def test_shorten_point_trims_sentences() -> None:
    long_point = "200 条/天重复写入的统计口径与改造后的观测周期、验收指标，以及灰度与回滚方案"

    shortened = shorten_point(long_point)

    assert len(shortened) == 33  # 32 chars + ellipsis
    assert shortened.endswith("…")


def test_shorten_point_keeps_short_points_and_collapses_whitespace() -> None:
    assert shorten_point("量化结果") == "量化结果"
    assert shorten_point("  量化\n结果  ") == "量化 结果"
