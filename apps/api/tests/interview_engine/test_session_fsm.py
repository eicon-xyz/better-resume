"""T2: session lifecycle transitions are exhaustive and fail loudly."""

from __future__ import annotations

import pytest

from better_resume.interview_engine.errors import IllegalSessionTransition
from better_resume.interview_engine.session_fsm import (
    SESSION_TRANSITIONS,
    SessionStatus,
    can_resume,
    ensure_transition,
)

ALLOWED = {
    ("draft", "resume_uploading"),
    ("draft", "abandoned"),
    ("resume_uploading", "ready"),
    ("resume_uploading", "draft"),
    ("resume_uploading", "abandoned"),
    ("ready", "in_progress"),
    ("ready", "abandoned"),
    ("in_progress", "finished"),
    ("in_progress", "abandoned"),
}


@pytest.mark.parametrize("source", list(SessionStatus))
@pytest.mark.parametrize("target", list(SessionStatus))
def test_transition_table_is_exhaustive(source: SessionStatus, target: SessionStatus) -> None:
    allowed = (source.value, target.value) in ALLOWED or source == target

    if allowed:
        ensure_transition(source, target)  # same-state is an idempotent no-op
    else:
        with pytest.raises(IllegalSessionTransition):
            ensure_transition(source, target)


def test_terminal_states_have_no_outgoing_edges() -> None:
    assert SESSION_TRANSITIONS[SessionStatus.FINISHED] == frozenset()
    assert SESSION_TRANSITIONS[SessionStatus.ABANDONED] == frozenset()


def test_only_ready_and_in_progress_can_resume() -> None:
    resumable = {status for status in SessionStatus if can_resume(status)}

    assert resumable == {SessionStatus.READY, SessionStatus.IN_PROGRESS}
