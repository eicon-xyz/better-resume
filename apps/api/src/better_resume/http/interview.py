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

from ..identity import Principal, current_principal
from ..interview_engine import (
    InterviewSession,
    InterviewSessionRepository,
    QuestionService,
    ResumeStorage,
)
from ..llm_gateway import LlmConfigError, ModelRegistry

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
    registry: ModelRegistry = state.model_registry

    try:
        spec = await registry.resolve(model_ref)
        api_key = registry.api_key(spec)
    except LlmConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc

    content = await file.read()
    if len(content) > MAX_RESUME_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="简历文件过大（上限 10MB）",
        )
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="简历文件为空")

    gateway = state.llm_gateway_factory(spec, api_key)
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


__all__ = ["MAX_RESUME_BYTES", "QuestionBatchView", "InterviewSessionView", "router"]
