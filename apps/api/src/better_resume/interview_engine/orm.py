"""SQLAlchemy rows for the interview module (M2 keeps both state layers in Postgres)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import (
    text as sa_text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class InterviewSessionRow(Base):
    __tablename__ = "interview_sessions"
    __table_args__ = (
        CheckConstraint(
            "status IN ("
            "'draft', 'resume_uploading', 'ready', 'in_progress', 'finished', 'abandoned'"
            ")",
            name="ck_interview_sessions_status",
        ),
        Index("ix_interview_sessions_user_id_status", "user_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft")
    interview_type: Mapped[str | None] = mapped_column(String(64))
    resume_path: Mapped[str | None] = mapped_column(String(512))
    resume_sha256: Mapped[str | None] = mapped_column(String(64))
    resume_size: Mapped[int | None] = mapped_column(Integer)
    resume_score: Mapped[float | None] = mapped_column(Float)
    question_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, server_default=sa_text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, server_default=sa_text("now()")
    )

    questions: Mapped[list[InterviewQuestionRow]] = relationship(
        back_populates="session", cascade="all, delete-orphan", passive_deletes=True
    )


class InterviewQuestionRow(Base):
    __tablename__ = "interview_questions"
    __table_args__ = (
        UniqueConstraint("session_id", "question_no", name="uq_interview_questions_session_no"),
        Index("ix_interview_questions_session_id_topic_no", "session_id", "topic_no"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("interview_sessions.id", ondelete="CASCADE"), nullable=False
    )
    question_no: Mapped[str] = mapped_column(String(16), nullable=False)
    topic_no: Mapped[int] = mapped_column(Integer, nullable=False)
    follow_up_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="main")
    text: Mapped[str] = mapped_column(Text, nullable=False)
    focus_points: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=sa_text("'[]'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, server_default=sa_text("now()")
    )

    session: Mapped[InterviewSessionRow] = relationship(back_populates="questions")


class InterviewAnswerRow(Base):
    __tablename__ = "interview_answers"
    __table_args__ = (
        # The idempotency gate: one row per client request, replay instead of re-charging.
        UniqueConstraint("session_id", "request_id", name="uq_interview_answers_session_request"),
        Index("ix_interview_answers_session_id_question_no", "session_id", "question_no"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("interview_sessions.id", ondelete="CASCADE"), nullable=False
    )
    question_no: Mapped[str] = mapped_column(String(16), nullable=False)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False, default="")
    score: Mapped[float | None] = mapped_column(Float)
    feedback: Mapped[str | None] = mapped_column(Text)
    missing_points: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=sa_text("'[]'::jsonb")
    )
    follow_up_needed: Mapped[bool | None] = mapped_column(Boolean)
    follow_up_reason: Mapped[str | None] = mapped_column(String(48))
    rule_version: Mapped[str | None] = mapped_column(String(16))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, server_default=sa_text("now()")
    )


class InterviewFlowStateRow(Base):
    __tablename__ = "interview_flow_state"
    __table_args__ = (
        CheckConstraint(
            "status IN ('init', 'asking', 'evaluating', 'follow_up', 'completed')",
            name="ck_interview_flow_state_status",
        ),
    )

    session_id: Mapped[str] = mapped_column(
        ForeignKey("interview_sessions.id", ondelete="CASCADE"), primary_key=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="init")
    current_index: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    current_question_no: Mapped[str | None] = mapped_column(String(16))
    total_questions: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    follow_up_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    max_follow_up: Mapped[int] = mapped_column(
        Integer, nullable=False, default=2, server_default="2"
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, server_default=sa_text("now()")
    )


class InterviewReportRow(Base):
    __tablename__ = "interview_reports"

    session_id: Mapped[str] = mapped_column(
        ForeignKey("interview_sessions.id", ondelete="CASCADE"), primary_key=True
    )
    overall_score: Mapped[float | None] = mapped_column(Float)
    dimensions: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=sa_text("'{}'::jsonb")
    )
    summary: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=sa_text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, server_default=sa_text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, server_default=sa_text("now()")
    )
