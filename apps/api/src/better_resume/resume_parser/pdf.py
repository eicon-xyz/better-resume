"""PDF -> TextBlock extraction (pdfplumber); the only place that touches PDF bytes."""

from __future__ import annotations

import io
from statistics import median

import pdfplumber
import structlog
from pydantic import BaseModel

from .errors import ResumeParseError

logger = structlog.get_logger("better_resume.resume_parser")

_LINE_TOLERANCE = 3.0
_WORD_GAP = 1.8


class TextBlock(BaseModel):
    """One visual line with the typographic hints the heuristics rely on."""

    text: str
    size: float
    bold: bool
    top: float
    page: int


def extract_blocks(data: bytes) -> list[TextBlock]:
    """Group words into lines, keeping size/bold/page so headings can be detected."""
    if not data.startswith(b"%PDF-"):
        raise ResumeParseError("not_a_pdf", "文件不是 PDF（缺少 %PDF- 头）")

    blocks: list[TextBlock] = []
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page_number, page in enumerate(pdf.pages, start=1):
                words = page.extract_words(extra_attrs=["size", "fontname"]) or []
                for line in _group_lines(words):
                    text = _join_words(line)
                    if not text:
                        continue
                    blocks.append(
                        TextBlock(
                            text=text,
                            size=float(median(word["size"] for word in line)),
                            bold=any("bold" in (word["fontname"] or "").lower() for word in line),
                            top=float(min(word["top"] for word in line)),
                            page=page_number,
                        )
                    )
    except ResumeParseError:
        raise
    except Exception as exc:  # noqa: BLE001 - pdfminer raises a zoo of exceptions
        logger.warning("resume_pdf_unreadable", error=str(exc))
        raise ResumeParseError("unreadable", f"PDF 无法解析：{exc}") from exc

    return sorted(blocks, key=lambda block: (block.page, block.top))


def _group_lines(words: list[dict]) -> list[list[dict]]:
    buckets: dict[tuple[int, int], list[dict]] = {}
    for word in words:
        key = (int(word.get("page_number") or 0), round(float(word["top"]) / _LINE_TOLERANCE))
        buckets.setdefault(key, []).append(word)
    return [
        sorted(bucket, key=lambda word: float(word["x0"])) for _, bucket in sorted(buckets.items())
    ]


def _join_words(words: list[dict]) -> str:
    """CJK runs have no gaps; latin runs are separated by visual whitespace."""
    parts: list[str] = []
    previous_x1: float | None = None
    for word in words:
        text = str(word["text"]).strip()
        if not text:
            continue
        if previous_x1 is not None and float(word["x0"]) - previous_x1 > _WORD_GAP:
            parts.append(" ")
        parts.append(text)
        previous_x1 = float(word["x1"])
    return "".join(parts).strip()
