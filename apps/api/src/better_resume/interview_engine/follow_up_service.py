"""Follow-up question generation (single level per topic: {topic}-F{n})."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..ai_resilience import AiResilience, Stage
from ..llm_gateway import ChatRequest, LlmGateway, Message
from .errors import InterviewEngineError
from .models import QuestionNo, QuestionRecord
from .orm import InterviewQuestionRow

logger = structlog.get_logger("better_resume.interview_engine")

FOLLOW_UP_SYSTEM_PROMPT = (
    "你是一名技术面试官。候选人在上一题的回答中留下了需要澄清的地方。请只针对缺失的要点，"
    "提出一个具体的追问，要求：\n"
    "1) 一句话，直接问，不要重复原题；\n"
    "2) 不要引入简历或回答中不存在的信息；\n"
    "3) 只输出 JSON：{text}。"
)


class FollowUpQuestion(BaseModel):
    """Structured output for one follow-up question."""

    text: str = Field(min_length=4, max_length=600)


def build_follow_up_messages(
    *, question_text: str, answer: str, missing_points: list[str]
) -> list[Message]:
    points = (
        "、".join(missing_points)
        if missing_points
        else "（模型未列出，请自行判断最值得澄清的一点）"
    )
    return [
        Message(role="system", content=FOLLOW_UP_SYSTEM_PROMPT),
        Message(
            role="user",
            content=(
                f"原题：{question_text}\n"
                f"候选人回答：{answer}\n"
                f"尚未覆盖的要点：{points}\n\n"
                "请给出 JSON 追问。"
            ),
        ),
    ]


class FollowUpService:
    def __init__(self, *, resilience: AiResilience) -> None:
        self._resilience = resilience

    async def generate_and_store(
        self,
        db: AsyncSession,
        *,
        session_id: str,
        topic_no: int,
        question_text: str,
        answer: str,
        missing_points: list[str],
        gateway: LlmGateway,
    ) -> QuestionRecord:
        next_index = await self._next_index(db, session_id, topic_no)
        question_no = str(QuestionNo(topic_no=topic_no, follow_up_index=next_index))

        request = ChatRequest(
            messages=build_follow_up_messages(
                question_text=question_text, answer=answer, missing_points=missing_points
            ),
            response_schema=FollowUpQuestion,
        )

        async def call() -> FollowUpQuestion:
            result = await gateway.complete(request)
            parsed = result.parsed
            if not isinstance(parsed, FollowUpQuestion):  # defensive: the gateway validates
                raise InterviewEngineError("follow-up question was not validated")
            return parsed

        payload = await self._resilience.run(
            Stage.FOLLOWUP, f"followup|{session_id}|{question_no}", call
        )

        now = datetime.now(UTC)
        row = InterviewQuestionRow(
            id=str(uuid.uuid4()),
            session_id=session_id,
            question_no=question_no,
            topic_no=topic_no,
            follow_up_index=next_index,
            kind="follow_up",
            text=payload.text,
            focus_points=list(missing_points),
            created_at=now,
        )
        db.add(row)
        await db.flush()
        logger.info("follow_up_generated", session_id=session_id, question_no=question_no)

        return QuestionRecord(
            id=row.id,
            session_id=session_id,
            question_no=question_no,
            topic_no=topic_no,
            follow_up_index=next_index,
            kind="follow_up",
            text=row.text,
            focus_points=list(row.focus_points or []),
            created_at=row.created_at,
        )

    @staticmethod
    async def _next_index(db: AsyncSession, session_id: str, topic_no: int) -> int:
        from sqlalchemy import func, select

        existing = (
            await db.execute(
                select(func.count())
                .select_from(InterviewQuestionRow)
                .where(
                    InterviewQuestionRow.session_id == session_id,
                    InterviewQuestionRow.topic_no == topic_no,
                    InterviewQuestionRow.follow_up_index > 0,
                )
            )
        ).scalar_one()
        return int(existing) + 1
