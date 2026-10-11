"""Question categories: the model proposes one, the engine decides (D23 / Q10).

The vendor label is advisory. Anything unrecognized or missing falls back to deterministic
rules over the parsed resume, so one stray label never fails a whole batch.
"""

from __future__ import annotations

from enum import StrEnum

from ..resume_parser import ResumeContext

#: Shortest marker worth matching (a company name or a project name).
_MIN_MARKER_LENGTH = 2


class QuestionCategory(StrEnum):
    """The three first-level categories every question carries."""

    FUNDAMENTALS = "fundamentals"
    PROJECT = "project"
    INTERNSHIP = "internship"


#: Display order of the three categories, everywhere they are listed.
DISPLAY_ORDER = (
    QuestionCategory.FUNDAMENTALS,
    QuestionCategory.PROJECT,
    QuestionCategory.INTERNSHIP,
)

CATEGORY_LABELS: dict[QuestionCategory, str] = {
    QuestionCategory.FUNDAMENTALS: "八股",
    QuestionCategory.PROJECT: "项目",
    QuestionCategory.INTERNSHIP: "实习",
}


class InterviewType(StrEnum):
    """The candidate's override of the question mix, chosen on the upload page (Q15)."""

    AUTO = "auto"
    FUNDAMENTALS = "fundamentals"
    PROJECT = "project"
    INTERNSHIP = "internship"


INTERVIEW_TYPE_LABELS: dict[InterviewType, str] = {
    InterviewType.AUTO: "自动（按简历）",
    InterviewType.FUNDAMENTALS: "八股基础",
    InterviewType.PROJECT: "项目深挖",
    InterviewType.INTERNSHIP: "实习深挖",
}


def coerce_interview_type(value: object) -> InterviewType:
    """Unknown, missing or malformed input means auto — a stale client must not block a session."""
    if isinstance(value, InterviewType):
        return value
    if isinstance(value, str):
        try:
            return InterviewType(value.strip().lower())
        except ValueError:
            return InterviewType.AUTO
    return InterviewType.AUTO


def coerce_category(value: object) -> QuestionCategory | None:
    """A vendor label -> enum member; unrecognized values become None."""
    if isinstance(value, QuestionCategory):
        return value
    if isinstance(value, str):
        try:
            return QuestionCategory(value.strip().lower())
        except ValueError:
            return None
    return None


def _internship_markers(context: ResumeContext) -> list[str]:
    """Company-level words from the internship entry, used to recognize a mention."""
    markers: list[str] = []
    for section in context.sections:
        if section.key != "internship":
            continue
        for bullet in section.bullets:
            head = bullet.strip(" -•·*\t").split(" ")[0]
            if len(head) >= _MIN_MARKER_LENGTH:
                markers.append(head)
    return markers


def infer_category(text: str, context: ResumeContext) -> QuestionCategory:
    """Rule fallback: internship entry -> internship, project name -> project, else fundamentals."""
    has_internship = any(section.key == "internship" for section in context.sections)
    if has_internship and (
        "实习" in text or any(marker in text for marker in _internship_markers(context))
    ):
        return QuestionCategory.INTERNSHIP
    for project in context.projects:
        if project.name and len(project.name) >= _MIN_MARKER_LENGTH and project.name in text:
            return QuestionCategory.PROJECT
    return QuestionCategory.FUNDAMENTALS


def decide_category(raw: object, *, text: str, context: ResumeContext) -> QuestionCategory:
    """The vendor's label when it is usable, otherwise the rule fallback."""
    return coerce_category(raw) or infer_category(text, context)


__all__ = [
    "CATEGORY_LABELS",
    "DISPLAY_ORDER",
    "INTERVIEW_TYPE_LABELS",
    "InterviewType",
    "QuestionCategory",
    "coerce_category",
    "coerce_interview_type",
    "decide_category",
    "infer_category",
]
