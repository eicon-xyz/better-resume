"""Question mix planning: what the resume supports, plus the candidate's override (Q8 / Q17).

The mix instructs the model; it never assigns categories positionally. Every question still
carries the category the model returned (validated and rule-checked in categories.py), and the
report shows the mix that actually happened.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..resume_parser import ResumeContext
from .categories import DISPLAY_ORDER, InterviewType, QuestionCategory
from .prompts import DEFAULT_QUESTIONS, clamp_count

#: How many slots an explicit "dig into projects / internships" choice reserves.
FOCUSED_SLOTS = 3


@dataclass(frozen=True)
class QuestionPlan:
    """How many questions of each category one interview aims for."""

    counts: dict[QuestionCategory, int]

    @property
    def total(self) -> int:
        return sum(self.counts.values())


def plan_questions(
    context: ResumeContext,
    *,
    count: int = DEFAULT_QUESTIONS,
    interview_type: InterviewType = InterviewType.AUTO,
) -> QuestionPlan:
    requested = clamp_count(count)
    has_project = bool(context.projects) or any(
        section.key == "projects" for section in context.sections
    )
    has_internship = any(section.key == "internship" for section in context.sections)

    if interview_type is InterviewType.FUNDAMENTALS:
        reserved = {QuestionCategory.FUNDAMENTALS: requested}
    elif interview_type is InterviewType.PROJECT:
        project = min(FOCUSED_SLOTS, requested) if has_project else 0
        reserved = {
            QuestionCategory.PROJECT: project,
            QuestionCategory.FUNDAMENTALS: requested - project,
        }
    elif interview_type is InterviewType.INTERNSHIP:
        internship = min(FOCUSED_SLOTS, requested) if has_internship else 0
        reserved = {
            QuestionCategory.INTERNSHIP: internship,
            QuestionCategory.FUNDAMENTALS: requested - internship,
        }
    else:
        reserved = _auto_mix(requested, has_project=has_project, has_internship=has_internship)

    return QuestionPlan(counts={category: reserved.get(category, 0) for category in DISPLAY_ORDER})


def _auto_mix(
    count: int, *, has_project: bool, has_internship: bool
) -> dict[QuestionCategory, int]:
    """Q17: one internship and two project questions when the resume supports them; the rest is
    fundamentals.
    """
    reserved = {
        QuestionCategory.INTERNSHIP: 1 if has_internship else 0,
        QuestionCategory.PROJECT: 2 if has_project else 0,
    }
    # Short interviews shrink the reserved slots rather than squeezing out fundamentals.
    while sum(reserved.values()) > count:
        if reserved[QuestionCategory.INTERNSHIP] > 0:
            reserved[QuestionCategory.INTERNSHIP] -= 1
        elif reserved[QuestionCategory.PROJECT] > 0:
            reserved[QuestionCategory.PROJECT] -= 1
        else:  # pragma: no cover - a non-negative sum below the count never enters the loop
            break
    reserved[QuestionCategory.FUNDAMENTALS] = count - sum(reserved.values())
    return reserved


__all__ = ["FOCUSED_SLOTS", "QuestionPlan", "plan_questions"]
