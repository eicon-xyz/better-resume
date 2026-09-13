"""Follow-up decision rule chain (§4.1.3) as a pure function — no LiteFlow, no IO."""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum

from pydantic import BaseModel, Field

RULE_VERSION = "m2.1"
DEFAULT_LOW_SCORE_THRESHOLD = 60.0


class FollowUpReason(StrEnum):
    AI_SUGGESTED = "AI_SUGGESTED"
    LOW_SCORE = "LOW_SCORE"
    MISSING_POINTS = "MISSING_POINTS"
    FOLLOW_UP_LIMIT_REACHED = "FOLLOW_UP_LIMIT_REACHED"
    INTERVIEW_COMPLETED = "INTERVIEW_COMPLETED"
    NO_RULE_TRIGGER = "NO_RULE_TRIGGER"


class FollowUpContext(BaseModel):
    """Everything the chain may look at; nothing else is allowed in."""

    interview_completed: bool
    follow_up_count: int = Field(ge=0)
    max_follow_up: int = Field(ge=0)
    ai_suggested: bool
    score: float | None = None
    missing_points: Sequence[str] = Field(default_factory=list)
    low_score_threshold: float = DEFAULT_LOW_SCORE_THRESHOLD


class FollowUpDecision(BaseModel):
    need_follow_up: bool
    reason_code: FollowUpReason
    resolved_max_follow_up: int
    terminated: bool = False
    fallback: bool = False
    rule_version: str = RULE_VERSION


def _run_chain(context: FollowUpContext) -> FollowUpDecision:
    """Guard nodes short-circuit the judges, exactly like the original chain order."""
    resolved_max = max(1, context.max_follow_up)

    # 1) completedStateGuard
    if context.interview_completed:
        return FollowUpDecision(
            need_follow_up=False,
            reason_code=FollowUpReason.INTERVIEW_COMPLETED,
            resolved_max_follow_up=resolved_max,
            terminated=True,
        )
    # 2) followUpLimitGuard
    if context.follow_up_count >= resolved_max:
        return FollowUpDecision(
            need_follow_up=False,
            reason_code=FollowUpReason.FOLLOW_UP_LIMIT_REACHED,
            resolved_max_follow_up=resolved_max,
            terminated=True,
        )
    # 3) aiSuggestionJudge
    if context.ai_suggested:
        return _need(FollowUpReason.AI_SUGGESTED, resolved_max)
    # 4) lowScoreJudge
    if context.score is not None and context.score < context.low_score_threshold:
        return _need(FollowUpReason.LOW_SCORE, resolved_max)
    # 5) missingPointsJudge
    if context.missing_points:
        return _need(FollowUpReason.MISSING_POINTS, resolved_max)
    # 6) finalize
    return FollowUpDecision(
        need_follow_up=False,
        reason_code=FollowUpReason.NO_RULE_TRIGGER,
        resolved_max_follow_up=resolved_max,
    )


def _need(reason: FollowUpReason, resolved_max: int) -> FollowUpDecision:
    return FollowUpDecision(
        need_follow_up=True, reason_code=reason, resolved_max_follow_up=resolved_max
    )


def decide_follow_up(context: FollowUpContext) -> FollowUpDecision:
    return _run_chain(context)


def decide_follow_up_or_fallback(context: FollowUpContext) -> FollowUpDecision:
    """Rule engines fail open: a broken chain must never invent a follow-up."""
    try:
        return _run_chain(context)
    except Exception:  # noqa: BLE001 - deliberate fail-open boundary
        return FollowUpDecision(
            need_follow_up=False,
            reason_code=FollowUpReason.NO_RULE_TRIGGER,
            resolved_max_follow_up=max(1, context.max_follow_up),
            fallback=True,
        )
