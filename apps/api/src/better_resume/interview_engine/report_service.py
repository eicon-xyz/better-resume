"""Report aggregation: deterministic dimensions + per-question replay (no LLM arithmetic)."""

from __future__ import annotations

import asyncio
import statistics
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import structlog
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..ai_resilience import AiResilience, Stage
from ..llm_gateway import ChatRequest, LlmGateway, Message
from .errors import SessionNotFound
from .models import InterviewSession, ReportRecord
from .orm import InterviewAnswerRow, InterviewQuestionRow, InterviewReportRow
from .session_fsm import SessionStatus
from .session_repo import InterviewSessionRepository

logger = structlog.get_logger("better_resume.interview_engine")

DIMENSION_LABELS = {
    "accuracy": "准确性",
    "depth": "深度",
    "coverage": "要点覆盖",
    "completeness": "完成度",
}

SUMMARY_SYSTEM_PROMPT = (
    "你是一名面试官，需要为一次模拟面试写 2-3 句总结。只依据给定的分数与要点数据，"
    "不要编造候选人没有说过的内容，也不要给出新的分数。只输出 JSON：{summary}。"
)


class ReportSummary(BaseModel):
    summary: str = Field(min_length=1, max_length=500)


@dataclass
class ReportResult:
    session: InterviewSession
    report: ReportRecord
    llm_summary_used: bool


def build_summary_messages(
    *, overall: float | None, dimensions: list[dict], missing: list[str]
) -> list[Message]:
    lines = [f"综合分：{overall if overall is not None else '无'}"]
    lines.extend(f"{item['label']}：{item['score']}" for item in dimensions)
    if missing:
        lines.append("反复缺失的要点：" + "、".join(sorted(set(missing))[:6]))
    return [
        Message(role="system", content=SUMMARY_SYSTEM_PROMPT),
        Message(role="user", content="\n".join(lines) + "\n\n请给出 JSON 总结。"),
    ]


class ReportService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        resilience: AiResilience,
    ) -> None:
        self._session_factory = session_factory
        self._resilience = resilience

    async def finish(self, *, session_id: str, user_id: str, gateway: LlmGateway) -> ReportResult:
        """Freeze the report once; every later call returns the same snapshot."""
        async with self._session_factory() as db:
            repo = InterviewSessionRepository(db)
            await repo.get_for_user(session_id, user_id)

            existing = await self._load_row(db, session_id)
            if existing is not None:
                session = await repo.get(session_id)
                return ReportResult(
                    session=session,
                    report=_to_record(existing),
                    llm_summary_used=bool(existing.summary),
                )

            payload = await self._aggregate(db, session_id)
        summary, used = await self._summarise(payload, gateway)

        async with self._session_factory() as db:
            repo = InterviewSessionRepository(db)
            session = await repo.get(session_id)
            if session.status is not SessionStatus.FINISHED:
                session = await repo.transition(session_id, SessionStatus.FINISHED)

            row = InterviewReportRow(
                session_id=session_id,
                overall_score=payload["overall_score"],
                dimensions={"items": payload["dimensions"]},
                summary=summary,
                payload={**payload, "summary": summary, "llm_summary_used": used},
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            db.add(row)
            await db.commit()
            record = _to_record(row)
            session = await repo.get(session_id)

        logger.info("interview_finished", session_id=session_id, overall=record.overall_score)
        return ReportResult(session=session, report=record, llm_summary_used=used)

    async def get_report(self, *, session_id: str, user_id: str) -> ReportRecord:
        async with self._session_factory() as db:
            await InterviewSessionRepository(db).get_for_user(session_id, user_id)
            row = await self._load_row(db, session_id)
        if row is None:
            raise SessionNotFound(f"report for {session_id} is not ready")
        return _to_record(row)

    # ---- internals --------------------------------------------------------------

    async def _load_row(self, db: AsyncSession, session_id: str) -> InterviewReportRow | None:
        return (
            await db.execute(
                select(InterviewReportRow).where(InterviewReportRow.session_id == session_id)
            )
        ).scalar_one_or_none()

    async def _aggregate(self, db: AsyncSession, session_id: str) -> dict:
        question_rows = (
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
        answer_rows = (
            (
                await db.execute(
                    select(InterviewAnswerRow)
                    .where(InterviewAnswerRow.session_id == session_id)
                    .order_by(InterviewAnswerRow.created_at)
                )
            )
            .scalars()
            .all()
        )
        answers_by_question = {row.question_no: row for row in answer_rows if row.score is not None}

        turns = []
        for question in question_rows:
            answer = answers_by_question.get(question.question_no)
            turns.append(
                {
                    "question_no": question.question_no,
                    "topic_no": question.topic_no,
                    "follow_up_index": question.follow_up_index,
                    "kind": "follow_up" if question.follow_up_index else "main",
                    "question": question.text,
                    "answer": answer.answer if answer else None,
                    "score": answer.score if answer else None,
                    "feedback": answer.feedback if answer else None,
                    "missing_points": list(answer.missing_points or []) if answer else [],
                    "follow_up_reason": answer.follow_up_reason if answer else None,
                }
            )

        main_scores = [t["score"] for t in turns if t["kind"] == "main" and t["score"] is not None]
        follow_up_scores = [
            t["score"] for t in turns if t["kind"] == "follow_up" and t["score"] is not None
        ]
        answered = len(main_scores)
        total_main = len([t for t in turns if t["kind"] == "main"])
        all_scores = main_scores + follow_up_scores
        missing_total = sum(len(t["missing_points"]) for t in turns if t["score"] is not None)
        scored_turns = len(all_scores)

        dimensions = _dimensions(
            main_scores=main_scores,
            follow_up_scores=follow_up_scores,
            answered=answered,
            total_main=total_main,
            missing_total=missing_total,
            scored_turns=scored_turns,
        )
        return {
            "session_id": session_id,
            "overall_score": round(statistics.fmean(all_scores), 1) if all_scores else None,
            "dimensions": dimensions,
            "turns": turns,
            "suggestions": _suggestions(turns, dimensions),
            "generated_at": datetime.now(UTC).isoformat(),
        }

    async def _summarise(self, payload: dict, gateway: LlmGateway) -> tuple[str | None, bool]:
        """The narrative is optional: a failure leaves the numbers untouched."""
        missing = [point for turn in payload["turns"] for point in turn["missing_points"]]

        async def call() -> ReportSummary:
            result = await gateway.complete(
                ChatRequest(
                    messages=build_summary_messages(
                        overall=payload["overall_score"],
                        dimensions=payload["dimensions"],
                        missing=missing,
                    ),
                    response_schema=ReportSummary,
                )
            )
            parsed = result.parsed
            if not isinstance(parsed, ReportSummary):
                raise SessionNotFound("summary was not validated")
            return parsed

        try:
            summary = await self._resilience.run(
                Stage.EVALUATION, f"report|{payload['session_id']}", call
            )
        except Exception as exc:  # noqa: BLE001 - the report must survive a vendor outage
            logger.warning("report_summary_failed", error=str(exc))
            return None, False
        return summary.summary, True


def _dimensions(
    *,
    main_scores: list[float],
    follow_up_scores: list[float],
    answered: int,
    total_main: int,
    missing_total: int,
    scored_turns: int,
) -> list[dict]:
    accuracy = statistics.fmean(main_scores) if main_scores else 0.0
    depth = statistics.fmean(follow_up_scores) if follow_up_scores else accuracy
    per_turn_missing = missing_total / scored_turns if scored_turns else 0.0
    coverage = max(0.0, 100.0 - 12.0 * per_turn_missing)
    completeness = 100.0 * answered / total_main if total_main else 0.0

    scores = {
        "accuracy": accuracy,
        "depth": depth,
        "coverage": coverage,
        "completeness": completeness,
    }
    return [
        {"key": key, "label": DIMENSION_LABELS[key], "score": round(value, 1)}
        for key, value in scores.items()
    ]


def _suggestions(turns: list[dict], dimensions: list[dict]) -> list[str]:
    by_key = {item["key"]: item["score"] for item in dimensions}
    tips: list[str] = []
    if by_key.get("coverage", 100) < 80:
        repeated = sorted({point for turn in turns for point in turn["missing_points"]})
        if repeated:
            tips.append("反复缺失的要点：" + "、".join(repeated[:4]))
    if by_key.get("depth", 100) < 70:
        tips.append("回答偏结论、缺过程：补充当时的取舍、失败尝试与量化结果")
    if by_key.get("completeness", 100) < 100:
        tips.append("有题目未作答，建议完整走完一轮面试再评估")
    if not tips:
        tips.append("表现稳定：继续保持用具体案例支撑结论的表达方式")
    return tips


def _to_record(row: InterviewReportRow) -> ReportRecord:
    payload = dict(row.payload or {})
    return ReportRecord(
        session_id=row.session_id,
        overall_score=row.overall_score,
        dimensions=payload.get("dimensions", (row.dimensions or {}).get("items", [])),
        summary=row.summary,
        turns=payload.get("turns", []),
        suggestions=payload.get("suggestions", []),
        payload=payload,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def _noop() -> None:  # pragma: no cover - keeps asyncio import meaningful for type checkers
    await asyncio.sleep(0)


def _new_id() -> str:  # pragma: no cover - helper for future callers
    return str(uuid.uuid4())
