"""Restore: rebuild the interview view from durable rows, deriving flow state when missing.

M2 keeps both state layers in Postgres, so restore is mostly a read; the derivation path
mirrors the old RehydrateService idea (exact vs derived confidence).
"""

from __future__ import annotations

import structlog
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .answer_repo import AnswerRepository
from .flow_fsm import FlowStatus
from .flow_store import FlowStateStore
from .hot_state import HotStateStore
from .models import AnswerRecord, FlowState, InterviewSession, QuestionRecord
from .orm import InterviewQuestionRow
from .session_repo import InterviewSessionRepository

logger = structlog.get_logger("better_resume.interview_engine")


class RestoreView(BaseModel):
    session: InterviewSession
    flow_status: FlowStatus
    current_question_no: str | None = None
    current_question: QuestionRecord | None = None
    answered: int = 0
    total_questions: int = 0
    last_result: AnswerRecord | None = None
    derived: bool = False
    #: M6: "hot" when served from the Redis cache, "derived" from Postgres.
    source: str = "derived"


class RestoreService:
    """One instance per request."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        hot_state: HotStateStore | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._hot_state = hot_state
        self._hot_ttl = 600

    async def restore(self, *, session_id: str, user_id: str) -> RestoreView:
        if self._hot_state is not None:
            cached = await self._hot_state.get(user_id=user_id, session_id=session_id)
            if cached is not None:
                return cached

        async with self._session_factory() as db:
            session = await InterviewSessionRepository(db).get_for_user(session_id, user_id)
            questions = await self._questions(db, session_id)
            answers = await AnswerRepository(db).list_for_session(session_id)
            scored = [answer for answer in answers if answer.score is not None]
            answered_numbers = {answer.question_no for answer in scored}

            flow = await FlowStateStore(db).load(session_id)
            derived = flow is None
            if flow is None:
                flow = await self._derive(db, session_id, questions, answered_numbers)
                await db.commit()

            current = next(
                (item for item in questions if item.question_no == flow.current_question_no), None
            )
            main_questions = [item for item in questions if item.kind == "main"]
            answered_main = len(
                [item for item in main_questions if item.question_no in answered_numbers]
            )

        view = RestoreView(
            session=session,
            flow_status=flow.status,
            current_question_no=flow.current_question_no,
            current_question=current,
            answered=answered_main,
            total_questions=flow.total_questions or len(main_questions),
            last_result=scored[-1] if scored else None,
            derived=derived,
        )
        if self._hot_state is not None:
            await self._hot_state.put(view, user_id=user_id, ttl_seconds=self._hot_ttl)
        return view

    async def _questions(self, db: AsyncSession, session_id: str) -> list[QuestionRecord]:
        rows = (
            (
                await db.execute(
                    select(InterviewQuestionRow)
                    .where(InterviewQuestionRow.session_id == session_id)
                    .order_by(InterviewQuestionRow.topic_no, InterviewQuestionRow.follow_up_index)
                )
            )
            .scalars()
            .all()
        )
        return [
            QuestionRecord(
                id=row.id,
                session_id=row.session_id,
                question_no=row.question_no,
                topic_no=row.topic_no,
                follow_up_index=row.follow_up_index,
                kind="follow_up" if row.follow_up_index else "main",
                text=row.text,
                focus_points=list(row.focus_points or []),
                created_at=row.created_at,
            )
            for row in rows
        ]

    async def _derive(
        self,
        db: AsyncSession,
        session_id: str,
        questions: list[QuestionRecord],
        answered_numbers: set[str],
    ) -> FlowState:
        """Rebuild the cursor from answers + questions, then write it back."""
        current_no = next(
            (item.question_no for item in questions if item.question_no not in answered_numbers),
            None,
        )
        if current_no is None:
            status = FlowStatus.COMPLETED
        else:
            current_question = next(item for item in questions if item.question_no == current_no)
            status = (
                FlowStatus.FOLLOW_UP if current_question.kind == "follow_up" else FlowStatus.ASKING
            )

        follow_up_count = 0
        if current_no is not None:
            topic_no = next(item.topic_no for item in questions if item.question_no == current_no)
            follow_up_count = len(
                [
                    item
                    for item in questions
                    if item.topic_no == topic_no
                    and item.kind == "follow_up"
                    and item.question_no in answered_numbers
                ]
            )

        logger.warning("flow_state_derived", session_id=session_id, current=current_no)
        return await FlowStateStore(db).initialize(
            session_id,
            total_questions=len([item for item in questions if item.kind == "main"]),
            max_follow_up=2,
            status=status,
            current_question_no=current_no,
            follow_up_count=follow_up_count,
        )
