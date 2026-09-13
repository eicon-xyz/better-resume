"""InterviewEngine seam: 4 public methods, the state machine is the only writer (§12.2)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .models import (
    AnswerTurn,
    ReportHandle,
    ResumeUpload,
    SessionHandle,
    SessionId,
    SessionView,
    TurnResult,
    UserId,
)


@runtime_checkable
class InterviewEngine(Protocol):
    async def start(self, user_id: UserId, resume: ResumeUpload) -> SessionHandle: ...

    async def answer(self, session_id: SessionId, turn: AnswerTurn) -> TurnResult: ...

    async def restore(self, session_id: SessionId) -> SessionView: ...

    async def finish(self, session_id: SessionId) -> ReportHandle: ...
