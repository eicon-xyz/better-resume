"""T9: per-category scoring in the report (Q7 / Q16)."""

from __future__ import annotations

from better_resume.interview_engine.report_service import category_breakdown


def turn(category: str | None, score: float | None) -> dict:
    return {"category": category, "score": score, "missing_points": []}


def test_breakdown_averages_a_category_and_marks_thin_ones() -> None:
    items = category_breakdown(
        [turn("project", 80.0), turn("project", 90.0), turn("fundamentals", 60.0)]
    )
    by_key = {item["key"]: item for item in items}

    assert by_key["project"]["score"] == 85.0
    assert by_key["project"]["count"] == 2
    assert by_key["project"]["comment"]
    assert by_key["project"]["label"] == "项目"
    assert by_key["fundamentals"]["count"] == 1
    assert by_key["fundamentals"]["score"] is None
    assert by_key["fundamentals"]["comment"] == "样本不足"


def test_breakdown_lists_every_category_even_when_absent() -> None:
    items = category_breakdown([])

    assert [item["key"] for item in items] == ["fundamentals", "project", "internship"]
    assert all(item["score"] is None for item in items)
    assert all(item["comment"] == "样本不足" for item in items)


def test_breakdown_ignores_unanswered_questions() -> None:
    items = category_breakdown([turn("project", None), turn("project", None)])
    project = next(item for item in items if item["key"] == "project")

    assert project["count"] == 0
    assert project["score"] is None


def test_breakdown_ignores_turns_without_a_category() -> None:
    items = category_breakdown([turn(None, 90.0), turn(None, 91.0)])

    assert all(item["count"] == 0 for item in items)
