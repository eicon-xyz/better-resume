"""HybridResumeParser: pdfplumber text -> heuristics -> ResumeContext (D10)."""

from __future__ import annotations

import structlog

from .errors import ResumeParseError
from .extractors import extract_contact, extract_projects, extract_skills
from .models import ResumeContext, Section
from .pdf import extract_blocks
from .sections import DetectedSection, split_document

logger = structlog.get_logger("better_resume.resume_parser")


class HybridResumeParser:
    """Deterministic parser: no LLM, no network, same bytes in -> same context out."""

    def parse(self, pdf: bytes) -> ResumeContext:
        blocks = extract_blocks(pdf)
        if not any(block.text.strip() for block in blocks):
            raise ResumeParseError(
                "text_layer_missing",
                "PDF 没有可提取的文本层（可能是扫描件或纯图片），请换一份可复制的简历",
            )

        split = split_document(blocks)
        full_text = "\n".join(block.text for block in blocks)
        header = split.header or full_text

        contact = extract_contact(header)
        skills = extract_skills(_section_text(split.sections, "skills") or full_text)
        projects = extract_projects(split.sections)

        warnings: list[str] = []
        if not split.sections:
            warnings.append("no_sections_detected")
        if not contact.email and not contact.phone:
            warnings.append("no_contact_found")
        if not skills:
            warnings.append("no_skills_found")

        logger.info(
            "resume_parsed",
            sections=[section.key for section in split.sections],
            skills=len(skills),
            projects=len(projects),
            warnings=warnings,
        )

        return ResumeContext(
            contact=contact,
            sections=[_to_section(section) for section in split.sections],
            skills=skills,
            projects=projects,
            warnings=warnings,
        )


def _section_text(sections: list[DetectedSection], key: str) -> str:
    return "\n".join(section.text for section in sections if section.key == key)


def _to_section(section: DetectedSection) -> Section:
    bullets = [line.strip(" -•·*\t") for line in section.text.splitlines() if line.strip()]
    return Section(
        title=section.title,
        key=section.key,
        bullets=[bullet for bullet in bullets if bullet],
    )
