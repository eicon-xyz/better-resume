"""T5: the follow-up rule chain is a pure function with an exhaustive decision table."""

from __future__ import annotations

import itertools

import pytest

from better_resume.interview_engine.follow_up import (
    RULE_VERSION,
    FollowUpContext,
    FollowUpReason,
    decide_follow_up,
    decide_follow_up_or_fallback,
)


def expected(
    *,
    completed: bool,
    follow_up_count: int,
    max_follow_up: int,
    ai_suggested: bool,
    score: float | None,
    missing_points: list[str],
    threshold: float = 60.0,
) -> tuple[bool, FollowUpReason]:
    """The rule chain written out independently of the implementation (§4.1.3 order)."""
    resolved = max(1, max_follow_up)
    if completed:
        return False, FollowUpReason.INTERVIEW_COMPLETED
    if follow_up_count >= resolved:
        return False, FollowUpReason.FOLLOW_UP_LIMIT_REACHED
    if ai_suggested:
        return True, FollowUpReason.AI_SUGGESTED
    if score is not None and score < threshold:
        return True, FollowUpReason.LOW_SCORE
    if missing_points:
        return True, FollowUpReason.MISSING_POINTS
    return False, FollowUpReason.NO_RULE_TRIGGER


@pytest.mark.parametrize(
    ("completed", "follow_up_count", "ai_suggested", "score", "missing"),
    list(
        itertools.product(
            [False, True],  # interview completed
            [0, 1, 2],  # follow-ups used
            [False, True],  # model suggested a follow-up
            [75.0, 40.0, None],  # score
            [[], ["要点缺失"]],  # missing points
        )
    ),
)
def test_decision_table_is_exhaustive(
    completed: bool,
    follow_up_count: int,
    ai_suggested: bool,
    score: float | None,
    missing: list[str],
) -> None:
    context = FollowUpContext(
        interview_completed=completed,
        follow_up_count=follow_up_count,
        max_follow_up=2,
        ai_suggested=ai_suggested,
        score=score,
        missing_points=missing,
    )

    decision = decide_follow_up(context)
    want_need, want_reason = expected(
        completed=completed,
        follow_up_count=follow_up_count,
        max_follow_up=2,
        ai_suggested=ai_suggested,
        score=score,
        missing_points=missing,
    )

    assert decision.need_follow_up is want_need
    assert decision.reason_code is want_reason
    assert decision.resolved_max_follow_up == 2
    assert decision.rule_version == RULE_VERSION
    assert decision.fallback is False


def test_completed_guard_short_circuits_everything() -> None:
    decision = decide_follow_up(
        FollowUpContext(
            interview_completed=True,
            follow_up_count=0,
            max_follow_up=2,
            ai_suggested=True,
            score=10.0,
            missing_points=["x"],
        )
    )

    assert decision.terminated is True
    assert decision.need_follow_up is False
    assert decision.reason_code is FollowUpReason.INTERVIEW_COMPLETED


def test_limit_guard_terminates_before_judging() -> None:
    decision = decide_follow_up(
        FollowUpContext(
            interview_completed=False,
            follow_up_count=2,
            max_follow_up=2,
            ai_suggested=True,
            score=0.0,
            missing_points=["x"],
        )
    )

    assert decision.terminated is True
    assert decision.reason_code is FollowUpReason.FOLLOW_UP_LIMIT_REACHED


def test_zero_max_follow_up_is_clamped_to_one() -> None:
    decision = decide_follow_up(
        FollowUpContext(
            interview_completed=False,
            follow_up_count=0,
            max_follow_up=0,
            ai_suggested=False,
            score=90.0,
            missing_points=[],
        )
    )

    assert decision.resolved_max_follow_up == 1
    assert decision.reason_code is FollowUpReason.NO_RULE_TRIGGER


def test_threshold_is_configurable() -> None:
    strict = decide_follow_up(
        FollowUpContext(
            interview_completed=False,
            follow_up_count=0,
            max_follow_up=2,
            ai_suggested=False,
            score=70.0,
            missing_points=[],
            low_score_threshold=80.0,
        )
    )

    assert strict.need_follow_up is True
    assert strict.reason_code is FollowUpReason.LOW_SCORE


def test_fail_open_when_the_chain_breaks(monkeypatch: pytest.MonkeyPatch) -> None:
    import better_resume.interview_engine.follow_up as module

    def boom(context: FollowUpContext) -> None:
        raise RuntimeError("rule engine exploded")

    monkeypatch.setattr(module, "_run_chain", boom)

    decision = decide_follow_up_or_fallback(
        FollowUpContext(
            interview_completed=False,
            follow_up_count=0,
            max_follow_up=2,
            ai_suggested=True,
            score=10.0,
            missing_points=["x"],
        )
    )

    assert decision.need_follow_up is False  # never invent a follow-up after a crash
    assert decision.fallback is True
    assert decision.reason_code is FollowUpReason.NO_RULE_TRIGGER


def test_question_number_round_trip() -> None:
    from better_resume.interview_engine import QuestionNo

    assert str(QuestionNo(topic_no=3)) == "3"
    assert str(QuestionNo(topic_no=3, follow_up_index=2)) == "3-F2"
    assert QuestionNo.parse("3").follow_up_index == 0
    assert QuestionNo.parse("3-F2").topic_no == 3
    assert QuestionNo.parse("3-F2").is_follow_up is True
    with pytest.raises(ValueError):
        QuestionNo.parse("F2")
