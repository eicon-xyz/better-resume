"""Question-generation prompts and the structured-output contract.

D10: the LLM only ever works on top of an already-parsed ResumeContext.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..llm_gateway import Message
from ..resume_parser import ResumeContext

MAX_QUESTIONS = 10
MIN_QUESTIONS = 1
DEFAULT_QUESTIONS = 5


class GeneratedQuestion(BaseModel):
    topic: str = Field(min_length=1, max_length=80)
    focus_points: list[str] = Field(min_length=1, max_length=6)
    text: str = Field(min_length=4, max_length=600)


class QuestionBatch(BaseModel):
    """Exactly what the vendor must return; validated before anything is written."""

    questions: list[GeneratedQuestion] = Field(min_length=1, max_length=MAX_QUESTIONS)
    resume_score: float = Field(ge=0, le=100)
    suggestions: list[str] = Field(default_factory=list, max_length=10)


SYSTEM_PROMPT = (
    "你是一名资深技术面试官。你会收到一份已经结构化好的候选人简历上下文，"
    "请据此设计面试题。严格要求：\n"
    "1) 只依据给定上下文出题，不得编造简历中不存在的经历或数据；\n"
    "2) 每道题必须给出 topic（考察主题）与 focus_points（希望听到的要点，1-6 条）；\n"
    "3) 题目要能区分「背过的」和「做过的」，优先追问项目细节、取舍与量化结果；\n"
    "4) 只输出 JSON 对象，字段为 questions[{topic, focus_points, text}]、"
    "resume_score、suggestions。"
)


def render_context(context: ResumeContext) -> str:
    """Deterministic digest of the parsed resume — the only thing the model may use."""
    lines: list[str] = []
    contact = context.contact
    if contact.name or contact.email:
        reachable = contact.email or contact.phone or "未提供"
        lines.append(f"姓名：{contact.name or '未知'}｜联系方式：{reachable}")
    for section in context.sections:
        if not section.bullets:
            continue
        lines.append(f"[{section.title}]")
        lines.extend(f"- {bullet}" for bullet in section.bullets[:12])
    if context.skills:
        lines.append(f"[技能] {'、'.join(context.skills[:30])}")
    for project in context.projects[:6]:
        detail = "；".join(project.highlights[:4])
        lines.append(f"[项目] {project.name}：{detail}" if detail else f"[项目] {project.name}")
    return "\n".join(lines)


def build_messages(
    context: ResumeContext, *, count: int = DEFAULT_QUESTIONS, language: str = "zh"
) -> list[Message]:
    requested = max(MIN_QUESTIONS, min(count, MAX_QUESTIONS))
    instruction = (
        f"请出 {requested} 道面试题，难度由浅入深，覆盖简历中最值得深挖的部分。"
        if language == "zh"
        else f"Produce {requested} interview questions, increasing in depth."
    )
    return [
        Message(role="system", content=SYSTEM_PROMPT),
        Message(
            role="user",
            content=f"{instruction}\n\n简历上下文：\n{render_context(context)}",
        ),
    ]


def clamp_count(count: int) -> int:
    return max(MIN_QUESTIONS, min(count, MAX_QUESTIONS))
