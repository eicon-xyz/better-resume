"""Interview HTTP surface: session lifecycle, resume upload and question generation."""

from __future__ import annotations

from datetime import datetime

import structlog
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from pydantic import BaseModel, Field
from sqlalchemy import select

from ..identity import Principal, current_principal
from ..interview_engine import (
    AnswerService,
    InterviewSession,
    InterviewSessionRepository,
    QuestionService,
    ReportRecord,
    ReportService,
    RestoreService,
    ResumeStorage,
)
from ..interview_engine.orm import InterviewQuestionRow
from ..llm_gateway import LlmScene
from .gateway import gateway_for

logger = structlog.get_logger("better_resume.interview_engine.http")

router = APIRouter(prefix="/api/v1/interview", tags=["interview"])

MAX_RESUME_BYTES = 10 * 1024 * 1024


class InterviewSessionCreateRequest(BaseModel):
    interview_type: str | None = Field(default=None, max_length=64)


class InterviewSessionView(BaseModel):
    id: str
    status: str
    interview_type: str | None = None
    question_count: int = 0
    resume_score: float | None = None
    created_at: datetime
    updated_at: datetime


class GeneratedQuestionView(BaseModel):
    question_no: str
    topic_no: int
    follow_up_index: int = 0
    kind: str = "main"
    text: str
    focus_points: list[str] = Field(default_factory=list)


class FlowView(BaseModel):
    status: str
    current_question_no: str | None = None
    total_questions: int = 0
    follow_up_count: int = 0
    max_follow_up: int = 2


class QuestionBatchView(BaseModel):
    session: InterviewSessionView
    questions: list[GeneratedQuestionView]
    suggestions: list[str] = Field(default_factory=list)
    flow: FlowView | None = None
    replayed: bool = False


def _session_view(session: InterviewSession) -> InterviewSessionView:
    return InterviewSessionView(
        id=session.id,
        status=session.status.value,
        interview_type=session.interview_type,
        question_count=session.question_count,
        resume_score=session.resume_score,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
async def create_session(
    payload: InterviewSessionCreateRequest,
    request: Request,
    principal: Principal = Depends(current_principal),  # noqa: B008
) -> InterviewSessionView:
    async with request.app.state.session_factory() as db:
        repo = InterviewSessionRepository(db)
        # One live interview per user: starting a new one abandons the previous.
        session = await repo.create(
            user_id=principal.user_id,
            interview_type=payload.interview_type,
            supersede_active=True,
        )
        await db.commit()
    return _session_view(session)


@router.get("/sessions")
async def list_sessions(
    request: Request,
    principal: Principal = Depends(current_principal),  # noqa: B008
    limit: int = Query(default=20, ge=1, le=100),
) -> list[InterviewSessionView]:
    async with request.app.state.session_factory() as db:
        sessions = await InterviewSessionRepository(db).list_active(principal.user_id)
    return [_session_view(session) for session in sessions[:limit]]


@router.post("/sessions/{session_id}/questions", status_code=status.HTTP_201_CREATED)
async def generate_questions(
    session_id: str,
    request: Request,
    file: UploadFile = File(...),  # noqa: B008
    count: int = Form(default=5, ge=1, le=10),
    model_ref: str | None = Form(default=None),
    principal: Principal = Depends(current_principal),  # noqa: B008
) -> QuestionBatchView:
    state = request.app.state

    gateway = await gateway_for(request, LlmScene.QUESTION_EXTRACTION, model_ref=model_ref)

    content = await file.read()
    if len(content) > MAX_RESUME_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="简历文件过大（上限 10MB）",
        )
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="简历文件为空")

    service = QuestionService(
        state.session_factory,
        resilience=state.ai_resilience,
        storage=ResumeStorage(state.settings.resume_storage_dir),
    )

    result = await service.generate(
        session_id=session_id,
        user_id=principal.user_id,
        resume_pdf=content,
        request_id=request.headers.get(state.settings.request_id_header) or "generation",
        gateway=gateway,
        count=count,
    )

    await _invalidate_hot(request, user_id=principal.user_id, session_id=session_id)
    return QuestionBatchView(
        session=_session_view(result.session),
        questions=[GeneratedQuestionView(**question) for question in result.questions],
        suggestions=result.suggestions,
        flow=(
            FlowView(
                status=result.flow.status.value,
                current_question_no=result.flow.current_question_no,
                total_questions=result.flow.total_questions,
                follow_up_count=result.flow.follow_up_count,
                max_follow_up=result.flow.max_follow_up,
            )
            if result.flow is not None
            else None
        ),
        replayed=result.replayed,
    )


class AnswerSubmitRequest(BaseModel):
    """One answer turn; `request_id` is the idempotency key (resend it when retrying)."""

    question_no: str = Field(min_length=1, max_length=16)
    answer: str = Field(min_length=1, max_length=8000)
    request_id: str = Field(min_length=1, max_length=64)
    model_ref: str | None = Field(default=None, max_length=64)


class AnswerView(BaseModel):
    question_no: str
    score: float | None = None
    feedback: str | None = None
    missing_points: list[str] = Field(default_factory=list)
    follow_up_needed: bool | None = None
    follow_up_reason: str | None = None
    rule_version: str | None = None
    error_message: str | None = None


class AnswerSubmitView(BaseModel):
    session: InterviewSessionView
    answer: AnswerView
    flow: FlowView
    next_action: str
    next_question_no: str | None = None
    next_question: GeneratedQuestionView | None = None
    replayed: bool = False


async def _invalidate_hot(request: Request, *, user_id: str, session_id: str) -> None:
    """Writes invalidate the hot view: a stale restore is worse than a slow one."""
    hot = getattr(request.app.state, "hot_state", None)
    if hot is not None:
        await hot.invalidate(user_id=user_id, session_id=session_id)


async def _load_question_view(
    request: Request, session_id: str, question_no: str | None
) -> GeneratedQuestionView | None:
    if question_no is None:
        return None
    async with request.app.state.session_factory() as db:
        row = (
            await db.execute(
                select(InterviewQuestionRow).where(
                    InterviewQuestionRow.session_id == session_id,
                    InterviewQuestionRow.question_no == question_no,
                )
            )
        ).scalar_one_or_none()
    if row is None:
        return None
    return GeneratedQuestionView(
        question_no=row.question_no,
        topic_no=row.topic_no,
        follow_up_index=row.follow_up_index,
        kind="follow_up" if row.follow_up_index else "main",
        text=row.text,
        focus_points=list(row.focus_points or []),
    )


@router.post("/sessions/{session_id}/answers", status_code=status.HTTP_201_CREATED)
async def submit_answer(
    session_id: str,
    payload: AnswerSubmitRequest,
    request: Request,
    principal: Principal = Depends(current_principal),  # noqa: B008
) -> AnswerSubmitView:
    state = request.app.state
    answer_gateway = await gateway_for(
        request, LlmScene.ANSWER_EVALUATION, model_ref=payload.model_ref
    )
    follow_up_gateway = await gateway_for(request, LlmScene.FOLLOW_UP, model_ref=payload.model_ref)

    service = AnswerService(
        state.session_factory,
        resilience=state.ai_resilience,
        locks=state.question_locks,
    )
    result = await service.submit(
        session_id=session_id,
        user_id=principal.user_id,
        question_no=payload.question_no,
        answer=payload.answer,
        request_id=payload.request_id,
        gateway=answer_gateway,
        follow_up_gateway=follow_up_gateway,
    )

    await _invalidate_hot(request, user_id=principal.user_id, session_id=session_id)
    return AnswerSubmitView(
        session=_session_view(result.session),
        answer=AnswerView(
            question_no=result.answer.question_no,
            score=result.answer.score,
            feedback=result.answer.feedback,
            missing_points=list(result.answer.missing_points),
            follow_up_needed=result.answer.follow_up_needed,
            follow_up_reason=result.answer.follow_up_reason,
            rule_version=result.answer.rule_version,
            error_message=result.answer.error_message,
        ),
        flow=FlowView(
            status=result.flow.status.value,
            current_question_no=result.flow.current_question_no,
            total_questions=result.flow.total_questions,
            follow_up_count=result.flow.follow_up_count,
            max_follow_up=result.flow.max_follow_up,
        ),
        next_action=result.next_action,
        next_question_no=result.next_question_no,
        next_question=await _load_question_view(request, session_id, result.next_question_no),
        replayed=result.replayed,
    )


__all__ = [
    "MAX_RESUME_BYTES",
    "AnswerSubmitView",
    "InterviewSessionView",
    "QuestionBatchView",
    "router",
]


class DimensionView(BaseModel):
    key: str
    label: str
    score: float


class ReportTurnView(BaseModel):
    question_no: str
    topic_no: int
    follow_up_index: int = 0
    kind: str = "main"
    question: str
    answer: str | None = None
    score: float | None = None
    feedback: str | None = None
    missing_points: list[str] = Field(default_factory=list)
    follow_up_reason: str | None = None


class InterviewReportView(BaseModel):
    session: InterviewSessionView
    overall_score: float | None = None
    dimensions: list[DimensionView] = Field(default_factory=list)
    turns: list[ReportTurnView] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    summary: str | None = None
    llm_summary_used: bool = False
    #: M6: the narrative is generated by the worker when jobs are enabled.
    summary_pending: bool = False


class RestoreResponseView(BaseModel):
    session: InterviewSessionView
    flow: FlowView
    current_question: GeneratedQuestionView | None = None
    answered: int = 0
    total_questions: int = 0
    last_answer: AnswerView | None = None
    derived: bool = False
    #: M6: whether this view came from the hot layer or was derived.
    source: str = "derived"


def _report_view(
    session: InterviewSession, report: ReportRecord, *, llm_summary_used: bool
) -> InterviewReportView:
    return InterviewReportView(
        session=_session_view(session),
        overall_score=report.overall_score,
        dimensions=[DimensionView(**item) for item in report.dimensions],
        turns=[ReportTurnView(**turn) for turn in report.turns],
        suggestions=list(report.suggestions),
        summary=report.summary,
        llm_summary_used=llm_summary_used,
    )


@router.get("/sessions/{session_id}/restore")
async def restore_session(
    session_id: str,
    request: Request,
    principal: Principal = Depends(current_principal),  # noqa: B008
) -> RestoreResponseView:
    state = request.app.state
    view = await RestoreService(state.session_factory, hot_state=state.hot_state).restore(
        session_id=session_id, user_id=principal.user_id
    )
    current = (
        GeneratedQuestionView(
            question_no=view.current_question.question_no,
            topic_no=view.current_question.topic_no,
            follow_up_index=view.current_question.follow_up_index,
            kind=view.current_question.kind,
            text=view.current_question.text,
            focus_points=list(view.current_question.focus_points),
        )
        if view.current_question is not None
        else None
    )
    last = view.last_result
    return RestoreResponseView(
        source=view.source,
        session=_session_view(view.session),
        flow=FlowView(
            status=view.flow_status.value,
            current_question_no=view.current_question_no,
            total_questions=view.total_questions,
        ),
        current_question=current,
        answered=view.answered,
        total_questions=view.total_questions,
        last_answer=(
            AnswerView(
                question_no=last.question_no,
                score=last.score,
                feedback=last.feedback,
                missing_points=list(last.missing_points),
                follow_up_needed=last.follow_up_needed,
                follow_up_reason=last.follow_up_reason,
                rule_version=last.rule_version,
                error_message=last.error_message,
            )
            if last is not None
            else None
        ),
        derived=view.derived,
    )


async def _resolve_gateway(request: Request, model_ref: str | None):
    """Report summary scene (kept as a helper so the endpoint stays readable)."""
    return await gateway_for(request, LlmScene.REPORT_SUMMARY, model_ref=model_ref)


@router.post("/sessions/{session_id}/finish", status_code=status.HTTP_201_CREATED)
async def finish_interview(
    session_id: str,
    request: Request,
    principal: Principal = Depends(current_principal),  # noqa: B008
    model_ref: str | None = Query(default=None),
) -> InterviewReportView:
    state = request.app.state
    if state.settings.jobs_enabled:
        # Queue the narrative and return the frozen numbers immediately (M6-T4).
        result = await ReportService(state.session_factory, resilience=state.ai_resilience).freeze(
            session_id=session_id, user_id=principal.user_id
        )
        await state.job_queue.enqueue(
            "report.summary",
            {"session_id": session_id, "user_id": principal.user_id},
            idempotency_key=f"report:{session_id}",
        )
        await _invalidate_hot(request, user_id=principal.user_id, session_id=session_id)
        return _report_view(
            result.session, result.report, llm_summary_used=result.llm_summary_used
        ).model_copy(update={"summary_pending": not result.llm_summary_used})

    # The synchronous path needs the gateway here; the queued path resolves it in the worker.
    gateway = await _resolve_gateway(request, model_ref)
    result = await ReportService(state.session_factory, resilience=state.ai_resilience).finish(
        session_id=session_id, user_id=principal.user_id, gateway=gateway
    )
    await _invalidate_hot(request, user_id=principal.user_id, session_id=session_id)
    return _report_view(result.session, result.report, llm_summary_used=result.llm_summary_used)


@router.get("/sessions/{session_id}/report")
async def get_report(
    session_id: str,
    request: Request,
    principal: Principal = Depends(current_principal),  # noqa: B008
) -> InterviewReportView:
    state = request.app.state
    service = ReportService(state.session_factory, resilience=state.ai_resilience)
    report = await service.get_report(session_id=session_id, user_id=principal.user_id)
    async with state.session_factory() as db:
        session = await InterviewSessionRepository(db).get_for_user(session_id, principal.user_id)
    return _report_view(session, report, llm_summary_used=bool(report.summary))


__all__ = [
    "MAX_RESUME_BYTES",
    "AnswerSubmitView",
    "InterviewReportView",
    "InterviewSessionView",
    "QuestionBatchView",
    "RestoreResponseView",
    "router",
]
