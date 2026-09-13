"""Explicit M0 placeholder; the state machine + scoring land with M2."""

from __future__ import annotations

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

_REASON = "InterviewEngine (flow state machine + scoring) is implemented in M2."


class UnimplementedInterviewEngine:
    async def start(self, user_id: UserId, resume: ResumeUpload) -> SessionHandle:
        raise NotImplementedError(_REASON)

    async def answer(self, session_id: SessionId, turn: AnswerTurn) -> TurnResult:
        raise NotImplementedError(_REASON)

    async def restore(self, session_id: SessionId) -> SessionView:
        raise NotImplementedError(_REASON)

    async def finish(self, session_id: SessionId) -> ReportHandle:
        raise NotImplementedError(_REASON)
