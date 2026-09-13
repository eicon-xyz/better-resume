"""InterviewSessionRepository: session lifecycle + ownership, FSM-guarded."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .errors import SessionNotFound
from .models import InterviewSession
from .orm import InterviewSessionRow
from .session_fsm import ACTIVE_STATUSES, SessionStatus, ensure_transition


def _utcnow() -> datetime:
    return datetime.now(UTC)


class InterviewSessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        user_id: str,
        interview_type: str | None = None,
        supersede_active: bool = False,
    ) -> InterviewSession:
        if supersede_active:
            await self.supersede_active(user_id)

        now = _utcnow()
        row = InterviewSessionRow(
            id=str(uuid.uuid4()),
            user_id=user_id,
            status=SessionStatus.DRAFT.value,
            interview_type=interview_type,
            question_count=0,
            created_at=now,
            updated_at=now,
        )
        self._session.add(row)
        await self._session.flush()
        return _to_model(row)

    async def get(self, session_id: str) -> InterviewSession:
        return _to_model(await self._fetch(session_id))

    async def get_for_user(self, session_id: str, user_id: str) -> InterviewSession:
        row = await self._fetch(session_id)
        if row.user_id != user_id:
            raise SessionNotFound(f"interview session {session_id} not found")
        return _to_model(row)

    async def list_active(self, user_id: str) -> list[InterviewSession]:
        stmt = (
            select(InterviewSessionRow)
            .where(
                InterviewSessionRow.user_id == user_id,
                InterviewSessionRow.status.in_([status.value for status in ACTIVE_STATUSES]),
            )
            .order_by(InterviewSessionRow.created_at.desc())
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_to_model(row) for row in rows]

    async def transition(self, session_id: str, target: SessionStatus) -> InterviewSession:
        row = await self._fetch(session_id, for_update=True)
        current = SessionStatus(row.status)
        ensure_transition(current, target)

        row.status = target.value
        row.updated_at = _utcnow()
        if target is SessionStatus.IN_PROGRESS and row.started_at is None:
            row.started_at = row.updated_at
        if target in (SessionStatus.FINISHED, SessionStatus.ABANDONED):
            row.finished_at = row.updated_at
        await self._session.flush()
        return _to_model(row)

    async def supersede_active(self, user_id: str) -> int:
        """Every other active session of this user becomes abandoned (one live interview)."""
        now = _utcnow()
        result = await self._session.execute(
            update(InterviewSessionRow)
            .where(
                InterviewSessionRow.user_id == user_id,
                InterviewSessionRow.status.in_([status.value for status in ACTIVE_STATUSES]),
            )
            .values(status=SessionStatus.ABANDONED.value, finished_at=now, updated_at=now)
        )
        await self._session.flush()
        return int(result.rowcount or 0)

    async def _fetch(self, session_id: str, *, for_update: bool = False) -> InterviewSessionRow:
        stmt = select(InterviewSessionRow).where(InterviewSessionRow.id == session_id)
        if for_update:
            stmt = stmt.with_for_update()
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            raise SessionNotFound(f"interview session {session_id} not found")
        return row


def _to_model(row: InterviewSessionRow) -> InterviewSession:
    return InterviewSession(
        id=row.id,
        user_id=row.user_id,
        status=SessionStatus(row.status),
        interview_type=row.interview_type,
        resume_path=row.resume_path,
        resume_sha256=row.resume_sha256,
        resume_size=row.resume_size,
        resume_score=row.resume_score,
        question_count=row.question_count,
        started_at=row.started_at,
        finished_at=row.finished_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
