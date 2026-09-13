"""Session lifecycle state machine (§4.1.1 layer 1): table-driven, no ORM here."""

from __future__ import annotations

from enum import StrEnum

from .errors import IllegalSessionTransition


class SessionStatus(StrEnum):
    DRAFT = "draft"
    RESUME_UPLOADING = "resume_uploading"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    FINISHED = "finished"
    ABANDONED = "abandoned"


# Explicit transition table: anything not listed is illegal (same-state is a no-op).
SESSION_TRANSITIONS: dict[SessionStatus, frozenset[SessionStatus]] = {
    SessionStatus.DRAFT: frozenset({SessionStatus.RESUME_UPLOADING, SessionStatus.ABANDONED}),
    SessionStatus.RESUME_UPLOADING: frozenset(
        {SessionStatus.READY, SessionStatus.DRAFT, SessionStatus.ABANDONED}
    ),
    SessionStatus.READY: frozenset({SessionStatus.IN_PROGRESS, SessionStatus.ABANDONED}),
    SessionStatus.IN_PROGRESS: frozenset({SessionStatus.FINISHED, SessionStatus.ABANDONED}),
    SessionStatus.FINISHED: frozenset(),
    SessionStatus.ABANDONED: frozenset(),
}

ACTIVE_STATUSES: frozenset[SessionStatus] = frozenset(
    {
        SessionStatus.DRAFT,
        SessionStatus.RESUME_UPLOADING,
        SessionStatus.READY,
        SessionStatus.IN_PROGRESS,
    }
)


def ensure_transition(current: SessionStatus, target: SessionStatus) -> None:
    """Raise unless the transition is allowed; the same status is always allowed."""
    if current == target:
        return
    if target not in SESSION_TRANSITIONS[current]:
        raise IllegalSessionTransition(f"illegal session transition: {current} -> {target}")


def can_resume(status: SessionStatus) -> bool:
    """Only a session with questions (ready) or an unfinished interview can be resumed."""
    return status in (SessionStatus.READY, SessionStatus.IN_PROGRESS)
