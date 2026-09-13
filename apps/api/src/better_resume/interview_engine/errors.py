"""Interview-engine failures; stable codes so the API layer can map them to HTTP status."""

from __future__ import annotations


class InterviewEngineError(Exception):
    """Base class for interview-engine failures."""


class SessionNotFound(InterviewEngineError):
    """Session missing, not owned by the caller, or filtered out by status."""


class QuestionNotFound(InterviewEngineError):
    """The requested question does not belong to the session."""


class IllegalSessionTransition(InterviewEngineError):
    """A session lifecycle transition that the state machine forbids."""


class IllegalFlowTransition(InterviewEngineError):
    """An answer-flow transition that the state machine forbids."""


class FlowStateMissing(InterviewEngineError):
    """Flow row is absent where the caller requires initialised state."""


class FlowConflict(InterviewEngineError):
    """Version CAS kept losing races beyond the retry budget."""
