"""Scoring prompts + the structured result contract (§4.1.2 step: evaluate)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..llm_gateway import Message

MAX_FEEDBACK_LENGTH = 2000
LOW_SCORE_THRESHOLD = 60.0


class ScoreResult(BaseModel):
    """What the scorer must return; validated before any state changes."""

    score: float = Field(ge=0, le=100)
    feedback: str = Field(min_length=1, max_length=MAX_FEEDBACK_LENGTH)
    missing_points: list[str] = Field(default_factory=list, max_length=10)
    follow_up_needed: bool = False


SCORING_SYSTEM_PROMPT = (
    "你是一名严格但公平的技术面试评分官。你会收到题目、考察要点与候选人的回答。请：\n"
    "1) 只依据回答本身评分，不要因为回答短就臆测候选人不会；\n"
    "2) 评分区间 0-100，60 分以下表示明显不达标；\n"
    "3) feedback 用中文写 2-4 句，指出具体优点与不足，不要空话；\n"
    "4) missing_points 列出回答中缺失的要点（可为空数组）；\n"
    "5) follow_up_needed 为 true 表示这个问题值得追问细节；\n"
    "6) 只输出 JSON：{score, feedback, missing_points, follow_up_needed}。"
)


def build_scoring_messages(
    *,
    question_text: str,
    focus_points: list[str],
    answer: str,
    language: str = "zh",
) -> list[Message]:
    points = "、".join(focus_points) if focus_points else "（未提供）"
    body = (
        f"题目：{question_text}\n考察要点：{points}\n候选人回答：{answer}\n\n请给出 JSON 评分结果。"
    )
    if language != "zh":  # pragma: no cover - M2 ships a Chinese prompt only
        body = f"Question: {question_text}\nFocus: {points}\nAnswer: {answer}\n\nReturn JSON."
    return [
        Message(role="system", content=SCORING_SYSTEM_PROMPT),
        Message(role="user", content=body),
    ]
