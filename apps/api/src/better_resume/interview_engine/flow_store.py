"""FlowStateStore: the only writer of flow state, guarded by version CAS (§4.1.1)."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .errors import FlowConflict, FlowStateMissing
from .flow_fsm import FlowStatus, ensure_flow_transition
from .models import FlowState
from .orm import InterviewFlowStateRow

DEFAULT_MAX_RETRIES = 12


def _utcnow() -> datetime:
    return datetime.now(UTC)


class FlowStateStore:
    """Per-request store bound to one AsyncSession; callers own the transaction."""

    def __init__(self, session: AsyncSession, *, max_retries: int = DEFAULT_MAX_RETRIES) -> None:
        self._session = session
        self._max_retries = max(1, max_retries)

    async def initialize(
        self, session_id: str, *, total_questions: int, max_follow_up: int = 2
    ) -> FlowState:
        now = _utcnow()
        row = InterviewFlowStateRow(
            session_id=session_id,
            status=FlowStatus.INIT.value,
            current_index=0,
            current_question_no=None,
            total_questions=total_questions,
            follow_up_count=0,
            max_follow_up=max(1, max_follow_up),
            version=1,
            updated_at=now,
        )
        self._session.add(row)
        await self._session.flush()
        return _to_model(row)

    async def load(self, session_id: str) -> FlowState | None:
        row = await self._fetch(session_id)
        return _to_model(row) if row is not None else None

    async def require(self, session_id: str) -> FlowState:
        state = await self.load(session_id)
        if state is None:
            raise FlowStateMissing(f"flow state missing for session {session_id}")
        return state

    async def mutate(self, session_id: str, mutate: Callable[[FlowState], FlowState]) -> FlowState:
        """Apply `mutate` under version CAS; retries when another writer wins the race."""
        for attempt in range(self._max_retries):
            row = await self._fetch(session_id)
            if row is None:
                raise FlowStateMissing(f"flow state missing for session {session_id}")

            current = _to_model(row)
            updated = mutate(current)
            ensure_flow_transition(current.status, updated.status)

            result = await self._session.execute(
                update(InterviewFlowStateRow)
                .where(
                    InterviewFlowStateRow.session_id == session_id,
                    InterviewFlowStateRow.version == current.version,
                )
                .values(
                    status=updated.status.value,
                    current_index=updated.current_index,
                    current_question_no=updated.current_question_no,
                    total_questions=updated.total_questions,
                    follow_up_count=updated.follow_up_count,
                    max_follow_up=updated.max_follow_up,
                    version=current.version + 1,
                    updated_at=_utcnow(),
                )
            )
            if result.rowcount == 1:
                await self._session.flush()
                return updated.model_copy(update={"version": current.version + 1})

            # Lost the race: back off a little so the winner can commit, then re-read.
            await asyncio.sleep(0.005 * (attempt + 1))

        raise FlowConflict(f"flow state for {session_id} kept changing under us")

    async def _fetch(self, session_id: str) -> InterviewFlowStateRow | None:
        return (
            await self._session.execute(
                select(InterviewFlowStateRow).where(InterviewFlowStateRow.session_id == session_id)
            )
        ).scalar_one_or_none()


def _to_model(row: InterviewFlowStateRow) -> FlowState:
    return FlowState(
        session_id=row.session_id,
        status=FlowStatus(row.status),
        current_index=row.current_index,
        current_question_no=row.current_question_no,
        total_questions=row.total_questions,
        follow_up_count=row.follow_up_count,
        max_follow_up=row.max_follow_up,
        version=row.version,
        updated_at=row.updated_at,
    )


def new_id() -> str:
    return str(uuid.uuid4())
