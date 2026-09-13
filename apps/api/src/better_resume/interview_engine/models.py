"""interview-engine value objects (§12.2). State-machine internals stay private in M2."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

UserId = str
SessionId = str


class ResumeUpload(BaseModel):
    filename: str
    content: bytes


class Question(BaseModel):
    kind: Literal["question"] = "question"
    question_no: int
    text: str


class FollowUp(BaseModel):
    kind: Literal["followup"] = "followup"
    question_no: int
    text: str
    missing_points: list[str] = Field(default_factory=list)


class Finished(BaseModel):
    kind: Literal["finished"] = "finished"


NextStep = Question | FollowUp | Finished


class AnswerTurn(BaseModel):
    """One submitted answer; `request_id` is the module's idempotency key."""

    request_id: str
    question_no: int
    text: str


class SessionHandle(BaseModel):
    session_id: SessionId
    status: str


class SessionView(BaseModel):
    session_id: SessionId
    status: str
    question_no: int
    answered: int


class TurnResult(BaseModel):
    score: float
    feedback: str
    missing_points: list[str] = Field(default_factory=list)
    next: NextStep


class ReportHandle(BaseModel):
    session_id: SessionId
    report_id: str
