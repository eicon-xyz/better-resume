"""interview-engine value objects (§12.2) + M2 persistence views."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from .flow_fsm import FlowStatus
from .session_fsm import SessionStatus

UserId = str
SessionId = str

_QUESTION_NO_RE = re.compile(r"^(?P<topic>\d+)(?:-F(?P<follow>\d+))?$")


class QuestionNo(BaseModel):
    """'3' for a main question, '3-F1' for its first follow-up (§4.1.2's numbering)."""

    topic_no: int = Field(ge=1)
    follow_up_index: int = Field(default=0, ge=0)

    def __str__(self) -> str:
        return (
            str(self.topic_no)
            if self.follow_up_index == 0
            else f"{self.topic_no}-F{self.follow_up_index}"
        )

    @property
    def is_follow_up(self) -> bool:
        return self.follow_up_index > 0

    @classmethod
    def parse(cls, raw: str) -> QuestionNo:
        match = _QUESTION_NO_RE.match(raw.strip())
        if match is None:
            raise ValueError(f"invalid question number: {raw!r}")
        return cls(
            topic_no=int(match.group("topic")),
            follow_up_index=int(match.group("follow") or 0),
        )


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


class InterviewSession(BaseModel):
    """Persistence view of one interview session (layer-1 status included)."""

    id: str
    user_id: str
    status: SessionStatus
    interview_type: str | None = None
    resume_path: str | None = None
    resume_sha256: str | None = None
    resume_size: int | None = None
    resume_score: float | None = None
    question_count: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class FlowState(BaseModel):
    """Layer-2 state: who is being asked what, and at which version (optimistic lock)."""

    session_id: str
    status: FlowStatus
    current_index: int = 0
    current_question_no: str | None = None
    total_questions: int = 0
    follow_up_count: int = 0
    max_follow_up: int = 2
    version: int = 1
    updated_at: datetime | None = None


class QuestionRecord(BaseModel):
    id: str
    session_id: str
    question_no: str
    topic_no: int
    follow_up_index: int = 0
    kind: Literal["main", "follow_up"] = "main"
    text: str
    focus_points: list[str] = Field(default_factory=list)
    created_at: datetime


class AnswerRecord(BaseModel):
    id: str
    session_id: str
    question_no: str
    request_id: str
    answer: str
    score: float | None = None
    feedback: str | None = None
    missing_points: list[str] = Field(default_factory=list)
    follow_up_needed: bool | None = None
    follow_up_reason: str | None = None
    rule_version: str | None = None
    error_message: str | None = None
    created_at: datetime


class ReportRecord(BaseModel):
    session_id: str
    overall_score: float | None = None
    dimensions: list[dict[str, Any]] = Field(default_factory=list)
    summary: str | None = None
    turns: list[dict[str, Any]] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
