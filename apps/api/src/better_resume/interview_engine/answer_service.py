"""Answer pipeline (§4.1.2).

idempotency gate -> question lock -> scoring -> flow advance/rollback.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..ai_resilience import AiResilience, Stage
from ..llm_gateway import ChatRequest, LlmGateway
from .answer_repo import AnswerRepository
from .errors import QuestionNotCurrent, QuestionNotFound, SessionNotFound
from .evaluation import ScoreResult, build_scoring_messages
from .flow_fsm import FlowStatus
from .flow_store import FlowStateStore
from .follow_up import (
    DEFAULT_LOW_SCORE_THRESHOLD,
    FollowUpContext,
    FollowUpDecision,
    decide_follow_up_or_fallback,
)
from .follow_up_service import FollowUpService
from .locks import QuestionLockRegistry
from .models import AnswerRecord, FlowState, InterviewSession, QuestionRecord
from .orm import InterviewQuestionRow
from .session_fsm import SessionStatus
from .session_repo import InterviewSessionRepository

logger = structlog.get_logger("better_resume.interview_engine")

NextAction = Literal["next_question", "follow_up", "finished"]

ANSWERABLE_STATUSES = {SessionStatus.READY, SessionStatus.IN_PROGRESS}


@dataclass
class AnswerResult:
    session: InterviewSession
    answer: AnswerRecord
    flow: FlowState
    next_action: NextAction
    next_question_no: str | None
    replayed: bool = False


def build_evaluation_key(session_id: str, question_no: str, answer: str) -> str:
    digest = hashlib.sha256(answer.encode("utf-8")).hexdigest()[:16]
    return f"evaluation|{session_id}|{question_no}|{digest}"


class AnswerService:
    """One instance per request; the whole turn is guarded by the question lock + FSM."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        resilience: AiResilience,
        locks: QuestionLockRegistry | None = None,
        low_score_threshold: float = DEFAULT_LOW_SCORE_THRESHOLD,
        decider: Callable[[FollowUpContext], FollowUpDecision] = decide_follow_up_or_fallback,
    ) -> None:
        self._session_factory = session_factory
        self._resilience = resilience
        self._locks = locks or QuestionLockRegistry()
        self._low_score_threshold = low_score_threshold
        self._decider = decider
        self._follow_ups = FollowUpService(resilience=resilience)

    async def submit(
        self,
        *,
        session_id: str,
        user_id: str,
        question_no: str,
        answer: str,
        request_id: str,
        gateway: LlmGateway,
        #: M5: follow-up questions may run on a different provider than scoring.
        follow_up_gateway: LlmGateway | None = None,
    ) -> AnswerResult:
        async with self._locks.acquire(session_id, question_no):
            return await self._submit_locked(
                session_id=session_id,
                user_id=user_id,
                question_no=question_no,
                answer=answer,
                request_id=request_id,
                gateway=gateway,
                follow_up_gateway=follow_up_gateway,
            )

    # ---- internals --------------------------------------------------------------

    async def _submit_locked(
        self,
        *,
        session_id: str,
        user_id: str,
        question_no: str,
        answer: str,
        request_id: str,
        gateway: LlmGateway,
        follow_up_gateway: LlmGateway | None = None,
    ) -> AnswerResult:
        async with self._session_factory() as db:
            repo = InterviewSessionRepository(db)
            await repo.get_for_user(session_id, user_id)
            # Second check inside the lock: the previous holder may have finished this turn.
            existing = await AnswerRepository(db).find_by_request(session_id, request_id)
            if existing is not None:
                return await self._replay(db, existing, session_id)
            session = await repo.require_status(
                session_id, ANSWERABLE_STATUSES, message="interview is not answerable"
            )
            if session.status is SessionStatus.READY:
                # First answer marks the interview as started, even if scoring then fails.
                await repo.transition(session_id, SessionStatus.IN_PROGRESS)
            question = await self._load_question(db, session_id, question_no)
            flow = await FlowStateStore(db).require(session_id)
            if flow.current_question_no != question_no:
                current = flow.current_question_no
                raise QuestionNotCurrent(
                    f"question {question_no} is not the current question ({current})"
                )
            await FlowStateStore(db).mutate(
                session_id,
                lambda current: current.model_copy(update={"status": FlowStatus.EVALUATING}),
            )
            await db.commit()

        try:
            score = await self._score(session_id, question_no, question, answer, gateway)
        except Exception as exc:
            await self._rollback_evaluation(
                session_id=session_id,
                question_no=question_no,
                request_id=request_id,
                answer=answer,
                error=exc,
            )
            raise

        try:
            return await self._persist_result(
                follow_up_gateway=follow_up_gateway or gateway,
                session_id=session_id,
                user_id=user_id,
                question_no=question_no,
                request_id=request_id,
                answer=answer,
                score=score,
                gateway=gateway,
            )
        except Exception as exc:
            # A failed follow-up (or any write error) must leave the question answerable.
            await self._rollback_evaluation(
                session_id=session_id,
                question_no=question_no,
                request_id=request_id,
                answer=answer,
                error=exc,
            )
            raise

    async def _load_question(
        self, db: AsyncSession, session_id: str, question_no: str
    ) -> QuestionRecord:
        row = (
            await db.execute(
                select(InterviewQuestionRow).where(
                    InterviewQuestionRow.session_id == session_id,
                    InterviewQuestionRow.question_no == question_no,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise QuestionNotFound(f"question {question_no} not found in session {session_id}")
        return QuestionRecord(
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

    async def _score(
        self,
        session_id: str,
        question_no: str,
        question: QuestionRecord,
        answer: str,
        gateway: LlmGateway,
    ) -> ScoreResult:
        request = ChatRequest(
            messages=build_scoring_messages(
                question_text=question.text,
                focus_points=question.focus_points,
                answer=answer,
            ),
            response_schema=ScoreResult,
        )

        async def call() -> ScoreResult:
            result = await gateway.complete(request)
            parsed = result.parsed
            if not isinstance(parsed, ScoreResult):  # defensive: the gateway validates
                raise QuestionNotFound("score was not validated")
            return parsed

        score = await self._resilience.run(
            Stage.EVALUATION,
            build_evaluation_key(session_id, question_no, answer),
            call,
        )
        logger.info(
            "answer_scored", session_id=session_id, question_no=question_no, score=score.score
        )
        return score

    async def _persist_result(
        self,
        *,
        follow_up_gateway: LlmGateway | None = None,
        session_id: str,
        user_id: str,
        question_no: str,
        request_id: str,
        answer: str,
        score: ScoreResult,
        gateway: LlmGateway,
    ) -> AnswerResult:
        async with self._session_factory() as db:
            repo = InterviewSessionRepository(db)
            answers = AnswerRepository(db)
            flow = await FlowStateStore(db).require(session_id)
            question = await self._load_question(db, session_id, question_no)

            decision = self._decider(
                FollowUpContext(
                    interview_completed=flow.status is FlowStatus.COMPLETED,
                    follow_up_count=flow.follow_up_count,
                    max_follow_up=flow.max_follow_up,
                    ai_suggested=bool(score.follow_up_needed),
                    score=score.score,
                    missing_points=list(score.missing_points),
                    low_score_threshold=self._low_score_threshold,
                )
            )
            logger.info(
                "follow_up_decided",
                session_id=session_id,
                question_no=question_no,
                need=decision.need_follow_up,
                reason=decision.reason_code.value,
                fallback=decision.fallback,
            )

            if decision.need_follow_up:
                follow_up = await self._follow_ups.generate_and_store(
                    db,
                    session_id=session_id,
                    topic_no=question.topic_no,
                    question_text=question.text,
                    answer=answer,
                    missing_points=list(score.missing_points),
                    gateway=follow_up_gateway or gateway,
                )
                next_question_no: str | None = follow_up.question_no
                next_action: NextAction = "follow_up"
                next_status = FlowStatus.FOLLOW_UP
                follow_up_count = flow.follow_up_count + 1
            else:
                next_question_no = await self._next_question_no(db, session_id, question_no)
                next_action = "next_question" if next_question_no else "finished"
                next_status = FlowStatus.ASKING if next_question_no else FlowStatus.COMPLETED
                follow_up_count = 0

            record = await answers.add(
                session_id=session_id,
                question_no=question_no,
                request_id=request_id,
                answer=answer,
                score=score.score,
                feedback=score.feedback,
                missing_points=list(score.missing_points),
                follow_up_needed=decision.need_follow_up,
                follow_up_reason=decision.reason_code.value,
                rule_version=decision.rule_version,
            )

            flow = await FlowStateStore(db).mutate(
                session_id,
                lambda current: current.model_copy(
                    update={
                        "status": next_status,
                        "current_question_no": next_question_no,
                        "follow_up_count": follow_up_count,
                        "current_index": current.current_index + 1,
                    }
                ),
            )
            await db.commit()
            refreshed = await repo.get(session_id)

        return AnswerResult(
            session=refreshed,
            answer=record,
            flow=flow,
            next_action=next_action,
            next_question_no=next_question_no,
        )

    async def _next_question_no(
        self, db: AsyncSession, session_id: str, question_no: str
    ) -> str | None:
        """Next main question by topic_no; follow-ups are decided in T5."""
        rows = (
            await db.execute(
                select(InterviewQuestionRow.question_no, InterviewQuestionRow.topic_no)
                .where(InterviewQuestionRow.session_id == session_id)
                .order_by(InterviewQuestionRow.topic_no, InterviewQuestionRow.follow_up_index)
            )
        ).all()
        current_topic = next((topic for number, topic in rows if number == question_no), None)
        if current_topic is None:
            return None
        following = [(topic, number) for number, topic in rows if topic > current_topic]
        return following[0][1] if following else None

    async def _replay(
        self, db: AsyncSession, existing: AnswerRecord, session_id: str
    ) -> AnswerResult:
        session = await InterviewSessionRepository(db).get(session_id)
        flow = await FlowStateStore(db).require(session_id)
        logger.info("answer_replayed", session_id=session_id, request_id=existing.request_id)
        return AnswerResult(
            session=session,
            answer=existing,
            flow=flow,
            next_action=_action_for(flow),
            next_question_no=flow.current_question_no,
            replayed=True,
        )

    async def _rollback_evaluation(
        self,
        *,
        session_id: str,
        question_no: str,
        request_id: str,
        answer: str,
        error: Exception,
    ) -> None:
        """Record the failed attempt and put the flow back so the question can be retried."""
        async with self._session_factory() as db:
            try:
                await AnswerRepository(db).add(
                    session_id=session_id,
                    question_no=question_no,
                    request_id=request_id,
                    answer=answer,
                    error_message=str(error) or error.__class__.__name__,
                )
                flow = await FlowStateStore(db).load(session_id)
                if flow is not None and flow.status is FlowStatus.EVALUATING:
                    await FlowStateStore(db).mutate(
                        session_id,
                        lambda current: current.model_copy(
                            update={"status": FlowStatus.ASKING, "current_question_no": question_no}
                        ),
                    )
                await db.commit()
            except SessionNotFound:  # pragma: no cover - session vanished
                await db.commit()
            logger.warning(
                "answer_evaluation_failed",
                session_id=session_id,
                question_no=question_no,
                error=str(error),
            )


def _action_for(flow: FlowState) -> NextAction:
    if flow.status is FlowStatus.COMPLETED:
        return "finished"
    if flow.status is FlowStatus.FOLLOW_UP:
        return "follow_up"
    return "next_question"


async def _noop() -> None:  # pragma: no cover - keeps asyncio import used in type-checking paths
    await asyncio.sleep(0)
