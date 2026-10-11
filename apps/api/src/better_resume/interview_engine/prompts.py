"""Question-generation prompts and the structured-output contract.

D10: the LLM only ever works on top of an already-parsed ResumeContext.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from pydantic import BaseModel, Field, field_validator

from ..llm_gateway import Message
from ..resume_parser import ResumeContext
from .categories import CATEGORY_LABELS, DISPLAY_ORDER, QuestionCategory, coerce_category
from .corpus import CorpusEntry

MAX_QUESTIONS = 10
MIN_QUESTIONS = 1
DEFAULT_QUESTIONS = 5


class GeneratedQuestion(BaseModel):
    topic: str = Field(min_length=1, max_length=80)
    category: QuestionCategory | None = None
    focus_points: list[str] = Field(min_length=1, max_length=6)
    text: str = Field(min_length=4, max_length=600)

    @field_validator("category", mode="before")
    @classmethod
    def _tolerate_an_unusable_label(cls, value: object) -> object:
        """A stray vendor label must not fail the batch: the engine falls back to rules (Q10)."""
        if value is None or isinstance(value, QuestionCategory):
            return value
        return coerce_category(value)


class QuestionBatch(BaseModel):
    """Exactly what the vendor must return; validated before anything is written."""

    questions: list[GeneratedQuestion] = Field(min_length=1, max_length=MAX_QUESTIONS)
    resume_score: float = Field(ge=0, le=100)
    suggestions: list[str] = Field(default_factory=list, max_length=10)


SYSTEM_PROMPT = (
    "你是一名资深技术面试官。你会收到一份已经结构化好的候选人简历上下文，"
    "请据此设计面试题。严格要求：\n"
    "1) 只依据给定上下文出题，不得编造简历中不存在的经历或数据；\n"
    "2) 每道题必须给出 topic（考察主题）、category 与 focus_points（希望听到的要点，1-6 条）；\n"
    "   category 只能取 fundamentals（八股基础）、project（简历里的项目经历）、"
    "internship（简历里的实习经历）；\n"
    "3) 题目要能区分「背过的」和「做过的」，优先追问项目细节、取舍与量化结果；\n"
    "4) 只输出 JSON 对象，字段为 questions[{topic, category, focus_points, text}]、"
    "resume_score、suggestions。"
)


#: Marks the reference-question block; a build-time corpus, never an online fetch (Q2.1).
CORPUS_BLOCK_TITLE = "参考题（八股语料，只作考点参考：不要照抄，也不要当成题库机械抽题）"


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
        lines.append(f"[{section.key}] {section.title}")
        lines.extend(f"- {bullet}" for bullet in section.bullets[:12])
    if context.skills:
        lines.append(f"[技能] {'、'.join(context.skills[:30])}")
    for project in context.projects[:6]:
        detail = "；".join(project.highlights[:4])
        lines.append(f"[项目] {project.name}：{detail}" if detail else f"[项目] {project.name}")
    return "\n".join(lines)


def render_corpus(corpus: Sequence[CorpusEntry]) -> str:
    """Reference questions handed to the model as inspiration, never as a fixed pool."""
    lines = [CORPUS_BLOCK_TITLE]
    lines.extend(f"- [{entry.topic}] {entry.question}" for entry in corpus)
    return "\n".join(lines)


def render_mix(mix: Mapping[QuestionCategory, int]) -> str:
    """One line telling the model how many questions of each category this interview wants."""
    wanted = "、".join(
        f"{CATEGORY_LABELS[category]} {mix.get(category, 0)} 道"
        for category in DISPLAY_ORDER
        if mix.get(category, 0) > 0
    )
    return f"本场类别配比：{wanted}；请让每道题的 category 落在这个分布里。"


def build_messages(
    context: ResumeContext,
    *,
    count: int = DEFAULT_QUESTIONS,
    language: str = "zh",
    corpus: Sequence[CorpusEntry] = (),
    mix: Mapping[QuestionCategory, int] | None = None,
) -> list[Message]:
    requested = max(MIN_QUESTIONS, min(count, MAX_QUESTIONS))
    instruction = (
        f"请出 {requested} 道面试题，难度由浅入深，覆盖简历中最值得深挖的部分。"
        if language == "zh"
        else f"Produce {requested} interview questions, increasing in depth."
    )
    parts = [instruction]
    if mix:
        parts.append(render_mix(mix))
    if corpus:
        parts.append(render_corpus(corpus))
    parts.append(f"简历上下文：\n{render_context(context)}")
    return [
        Message(role="system", content=SYSTEM_PROMPT),
        Message(role="user", content="\n\n".join(parts)),
    ]


def clamp_count(count: int) -> int:
    return max(MIN_QUESTIONS, min(count, MAX_QUESTIONS))
