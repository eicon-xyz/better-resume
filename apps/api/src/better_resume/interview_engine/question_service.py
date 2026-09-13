"""Question generation: ResumeContext -> validated batch -> persisted questions (§7.3 stage 1)."""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..ai_resilience import AiResilience, Stage
from ..llm_gateway import ChatRequest, LlmGateway
from ..resume_parser import HybridResumeParser, ResumeContext
from .errors import GenerationInProgress, InterviewEngineError, SessionNotFound
from .flow_fsm import FlowStatus
from .flow_store import FlowStateStore
from .models import FlowState, InterviewSession, QuestionRecord
from .orm import InterviewQuestionRow
from .prompts import QuestionBatch, build_messages, clamp_count
from .session_fsm import SessionStatus
from .session_repo import InterviewSessionRepository
from .storage import ResumeStorage, StoredResume

logger = structlog.get_logger("better_resume.interview_engine")


@dataclass
class QuestionGenerationResult:
    session: InterviewSession
    questions: list[dict]
    suggestions: list[str]
    flow: FlowState | None
    replayed: bool


def build_generation_key(session_id: str, *, resume_digest: str, count: int, language: str) -> str:
    """stage|session|count|language|sha256(resume) — every input the prompt depends on.

    The M2 version keyed on session + email/name only, so a different resume (or a
    different question count) could hit a cached batch once replay is switched on.
    """
    digest = hashlib.sha256(resume_digest.encode("utf-8")).hexdigest()[:16]
    return f"extraction|{session_id}|{count}|{language}|{digest}"


def _resume_digest(context: ResumeContext, stored: StoredResume | None) -> str:
    """Prefer the stored file hash; fall back to the parsed context for synthetic uploads."""
    if stored is not None and getattr(stored, "sha256", None):
        return str(stored.sha256)
    return context.model_dump_json()


class QuestionService:
    """One instance per request; the whole generation is one transaction."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        resilience: AiResilience,
        storage: ResumeStorage | None = None,
        parser: HybridResumeParser | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._resilience = resilience
        self._storage = storage or ResumeStorage(Path("data/resumes"))
        self._parser = parser or HybridResumeParser()

    async def generate(
        self,
        *,
        session_id: str,
        user_id: str,
        resume_pdf: bytes | None = None,
        request_id: str,
        gateway: LlmGateway,
        count: int = 5,
        language: str = "zh",
    ) -> QuestionGenerationResult:
        requested = clamp_count(count)

        async with self._session_factory() as db:
            repo = InterviewSessionRepository(db)
            session = await repo.get_for_user(session_id, user_id)

            if session.question_count > 0:
                return await self._replay(db, session)
            if session.status is SessionStatus.RESUME_UPLOADING:
                # Another generation is holding this session right now.
                raise GenerationInProgress(
                    f"question generation already in progress for session {session_id}"
                )

            # Claim the session: concurrent generations now fail this check instead of racing.
            session = await repo.transition(session_id, SessionStatus.RESUME_UPLOADING)
            stored_resume = self._store_resume(session.user_id, resume_pdf)
            await db.commit()

        try:
            context = await asyncio.to_thread(self._parse, resume_pdf, stored_resume)
            batch = await self._ask_model(
                session_id,
                context,
                requested,
                gateway,
                language,
                resume_digest=_resume_digest(context, stored_resume),
            )
        except Exception:
            await self._rollback_to_draft(session_id)
            raise

        try:
            return await self._persist(
                session_id=session_id,
                request_id=request_id,
                batch=batch,
                stored_resume=stored_resume,
                resume_score=batch.resume_score,
            )
        except Exception:
            await self._rollback_to_draft(session_id)
            raise

    # ---- internals --------------------------------------------------------------

    def _store_resume(self, user_id: str, resume_pdf: bytes | None) -> StoredResume | None:
        if resume_pdf is None:
            return None
        return self._storage.save(user_id=user_id, content=resume_pdf)

    def _parse(self, resume_pdf: bytes | None, stored: StoredResume | None) -> ResumeContext:
        data = (
            resume_pdf
            if resume_pdf is not None
            else self._storage.read(stored.path if stored else "")
        )
        return self._parser.parse(data)

    async def _ask_model(
        self,
        session_id: str,
        context: ResumeContext,
        count: int,
        gateway: LlmGateway,
        language: str,
        *,
        resume_digest: str,
    ) -> QuestionBatch:
        request = ChatRequest(
            messages=build_messages(context, count=count, language=language),
            response_schema=QuestionBatch,
        )
        key = build_generation_key(
            session_id, resume_digest=resume_digest, count=count, language=language
        )

        async def call() -> QuestionBatch:
            result = await gateway.complete(request)
            parsed = result.parsed
            if not isinstance(parsed, QuestionBatch):  # defensive: the gateway enforces the schema
                raise InterviewEngineError("question batch was not validated")
            return parsed

        batch = await self._resilience.run(Stage.EXTRACTION, key, call)
        logger.info("questions_generated", session_id=session_id, count=len(batch.questions))
        return batch

    async def _persist(
        self,
        *,
        session_id: str,
        request_id: str,
        batch: QuestionBatch,
        stored_resume: StoredResume | None,
        resume_score: float,
    ) -> QuestionGenerationResult:
        now = datetime.now(UTC)
        async with self._session_factory() as db:
            repo = InterviewSessionRepository(db)
            await repo.get(session_id)  # existence check; raises SessionNotFound

            rows = []
            for index, question in enumerate(batch.questions, start=1):
                rows.append(
                    InterviewQuestionRow(
                        id=str(uuid.uuid4()),
                        session_id=session_id,
                        question_no=str(index),
                        topic_no=index,
                        follow_up_index=0,
                        kind="main",
                        text=question.text,
                        focus_points=list(question.focus_points),
                        created_at=now,
                    )
                )
            db.add_all(rows)

            updates: dict[str, object] = {
                "question_count": len(rows),
                "resume_score": resume_score,
            }
            if stored_resume is not None:
                updates |= {
                    "resume_path": stored_resume.path,
                    "resume_sha256": stored_resume.sha256,
                    "resume_size": stored_resume.size,
                }
            await repo.update(session_id, **updates)

            flow = await FlowStateStore(db).initialize(
                session_id,
                total_questions=len(rows),
                max_follow_up=2,
                status=FlowStatus.ASKING,
                current_question_no="1",
            )
            await db.flush()
            await repo.transition(session_id, SessionStatus.READY)
            await db.commit()

            questions = [
                {
                    "question_no": row.question_no,
                    "topic_no": row.topic_no,
                    "follow_up_index": row.follow_up_index,
                    "kind": row.kind,
                    "text": row.text,
                    "focus_points": list(row.focus_points),
                }
                for row in rows
            ]
            refreshed = await InterviewSessionRepository(db).get(session_id)

        return QuestionGenerationResult(
            session=refreshed,
            questions=questions,
            suggestions=list(batch.suggestions),
            flow=flow.model_copy(update={"total_questions": len(rows)}),
            replayed=False,
        )

    async def _replay(
        self, db: AsyncSession, session: InterviewSession
    ) -> QuestionGenerationResult:
        rows = (
            (
                await db.execute(
                    select(InterviewQuestionRow)
                    .where(InterviewQuestionRow.session_id == session.id)
                    .order_by(InterviewQuestionRow.topic_no, InterviewQuestionRow.follow_up_index)
                )
            )
            .scalars()
            .all()
        )
        flow = await FlowStateStore(db).load(session.id)
        logger.info("question_generation_replayed", session_id=session.id, count=len(rows))
        return QuestionGenerationResult(
            session=session,
            questions=[
                {
                    "question_no": row.question_no,
                    "topic_no": row.topic_no,
                    "follow_up_index": row.follow_up_index,
                    "kind": row.kind,
                    "text": row.text,
                    "focus_points": list(row.focus_points),
                }
                for row in rows
            ],
            suggestions=[],
            flow=flow,
            replayed=True,
        )

    async def _rollback_to_draft(self, session_id: str) -> None:
        """Failure must be retryable: drop any partial rows and put the session back."""
        async with self._session_factory() as db:
            await db.execute(
                delete(InterviewQuestionRow).where(InterviewQuestionRow.session_id == session_id)
            )
            try:
                session = await InterviewSessionRepository(db).get(session_id)
            except SessionNotFound:  # pragma: no cover - session vanished mid-flight
                await db.commit()
                return
            if session.status is SessionStatus.RESUME_UPLOADING:
                await InterviewSessionRepository(db).transition(session_id, SessionStatus.DRAFT)
            await db.commit()


__all__ = ["QuestionGenerationResult", "QuestionService", "QuestionRecord", "build_generation_key"]
