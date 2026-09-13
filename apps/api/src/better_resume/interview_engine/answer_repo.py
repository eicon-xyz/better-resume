"""AnswerRepository: idempotent answer rows (uniqueness is enforced by the database)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import AnswerRecord
from .orm import InterviewAnswerRow


def _utcnow() -> datetime:
    return datetime.now(UTC)


class AnswerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        *,
        session_id: str,
        question_no: str,
        request_id: str,
        answer: str,
        score: float | None = None,
        feedback: str | None = None,
        missing_points: list[str] | None = None,
        follow_up_needed: bool | None = None,
        follow_up_reason: str | None = None,
        rule_version: str | None = None,
        error_message: str | None = None,
    ) -> AnswerRecord:
        row = InterviewAnswerRow(
            id=str(uuid.uuid4()),
            session_id=session_id,
            question_no=question_no,
            request_id=request_id,
            answer=answer,
            score=score,
            feedback=feedback,
            missing_points=missing_points or [],
            follow_up_needed=follow_up_needed,
            follow_up_reason=follow_up_reason,
            rule_version=rule_version,
            error_message=error_message,
            created_at=_utcnow(),
        )
        self._session.add(row)
        await self._session.flush()
        return _to_model(row)

    async def find_by_request(self, session_id: str, request_id: str) -> AnswerRecord | None:
        row = (
            await self._session.execute(
                select(InterviewAnswerRow).where(
                    InterviewAnswerRow.session_id == session_id,
                    InterviewAnswerRow.request_id == request_id,
                )
            )
        ).scalar_one_or_none()
        return _to_model(row) if row is not None else None

    async def find_by_question(self, session_id: str, question_no: str) -> AnswerRecord | None:
        row = (
            await self._session.execute(
                select(InterviewAnswerRow)
                .where(
                    InterviewAnswerRow.session_id == session_id,
                    InterviewAnswerRow.question_no == question_no,
                )
                .order_by(InterviewAnswerRow.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        return _to_model(row) if row is not None else None

    async def list_for_session(self, session_id: str) -> list[AnswerRecord]:
        rows = (
            (
                await self._session.execute(
                    select(InterviewAnswerRow)
                    .where(InterviewAnswerRow.session_id == session_id)
                    .order_by(InterviewAnswerRow.created_at)
                )
            )
            .scalars()
            .all()
        )
        return [_to_model(row) for row in rows]

    async def update_result(
        self,
        answer_id: str,
        *,
        score: float | None,
        feedback: str | None,
        missing_points: list[str],
        follow_up_needed: bool | None,
        follow_up_reason: str | None,
        rule_version: str | None,
        error_message: str | None = None,
    ) -> AnswerRecord:
        row = (
            await self._session.execute(
                select(InterviewAnswerRow).where(InterviewAnswerRow.id == answer_id)
            )
        ).scalar_one()
        row.score = score
        row.feedback = feedback
        row.missing_points = missing_points
        row.follow_up_needed = follow_up_needed
        row.follow_up_reason = follow_up_reason
        row.rule_version = rule_version
        row.error_message = error_message
        await self._session.flush()
        return _to_model(row)


def _to_model(row: InterviewAnswerRow) -> AnswerRecord:
    return AnswerRecord(
        id=row.id,
        session_id=row.session_id,
        question_no=row.question_no,
        request_id=row.request_id,
        answer=row.answer,
        score=row.score,
        feedback=row.feedback,
        missing_points=list(row.missing_points or []),
        follow_up_needed=row.follow_up_needed,
        follow_up_reason=row.follow_up_reason,
        rule_version=row.rule_version,
        error_message=row.error_message,
        created_at=row.created_at,
    )


def _as_dict(value: Any) -> dict[str, Any]:  # pragma: no cover - helper kept for symmetry
    return value if isinstance(value, dict) else {}
