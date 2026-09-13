"""Heading heuristics: keyword + typography scoring, with a deterministic fallback.

Deliberately no LLM here (D10): parsing must be reproducible and testable.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel

from .pdf import TextBlock

# Canonical section keys -> keywords (lower-cased matching for latin text).
SECTION_KEYWORDS: dict[str, tuple[str, ...]] = {
    "education": ("教育", "学历", "education", "academic"),
    "experience": ("工作经历", "工作经验", "实习经历", "实习", "experience", "employment"),
    "projects": ("项目", "project"),
    "skills": ("技能", "擅长的技术", "skills", "technical skills"),
    "summary": ("自我评价", "个人简介", "个人总结", "summary", "about me", "profile"),
    "awards": ("获奖", "荣誉", "awards", "honors"),
}

_MAX_HEADING_LENGTH = 20
_HEADING_SIZE_RATIO = 1.12


class DetectedSection(BaseModel):
    key: str
    title: str
    text: str


class SectionSplit(BaseModel):
    header: str
    sections: list[DetectedSection]


def body_size(blocks: Sequence[TextBlock]) -> float:
    """Baseline = smallest size among prose-length lines (short display text is ignored)."""
    prose = [block.size for block in blocks if len(block.text.strip()) > 12]
    candidates = prose or [block.size for block in blocks]
    return min(candidates) if candidates else 0.0


def keyword_key(text: str) -> str | None:
    normalized = text.strip().lower()
    for key, keywords in SECTION_KEYWORDS.items():
        if any(keyword in normalized for keyword in keywords):
            return key
    return None


def is_heading(block: TextBlock, baseline: float) -> str | None:
    text = block.text.strip()
    if not text or len(text) > _MAX_HEADING_LENGTH:
        return None
    key = keyword_key(text)
    if key is None:
        return None
    emphasized = block.bold or (baseline > 0 and block.size >= baseline * _HEADING_SIZE_RATIO)
    return key if emphasized else None


def split_document(blocks: Sequence[TextBlock]) -> SectionSplit:
    """Leading content before the first heading is header material (contact, name)."""
    ordered = sorted(blocks, key=lambda block: (block.page, block.top))
    baseline = body_size(ordered)

    header_lines: list[str] = []
    sections: list[DetectedSection] = []
    current: DetectedSection | None = None

    for block in ordered:
        text = block.text.strip()
        if not text:
            continue
        key = is_heading(block, baseline)
        if key is not None:
            current = DetectedSection(key=key, title=text, text="")
            sections.append(current)
            continue
        if current is None:
            header_lines.append(text)
        else:
            current.text = f"{current.text}\n{text}".strip()

    return SectionSplit(header="\n".join(header_lines), sections=sections)


def split_sections(blocks: Sequence[TextBlock]) -> list[DetectedSection]:
    """Sections if any heading was found, otherwise one honest catch-all section."""
    split = split_document(blocks)
    if split.sections:
        return split.sections

    everything = "\n".join(block.text.strip() for block in blocks if block.text.strip())
    return [DetectedSection(key="other", title="其他", text=everything)] if everything else []
