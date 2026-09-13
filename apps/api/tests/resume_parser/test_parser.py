"""T1: end-to-end parsing of generated PDFs (English + CJK) and failure modes."""

from __future__ import annotations

import pytest

from better_resume.resume_parser import HybridResumeParser, ResumeParseError
from better_resume.resume_parser.pdf import extract_blocks

from .conftest import build_pdf

ENGLISH_LINES = [
    ("Jane Doe", 18, True),
    ("jane.doe@example.com | 13800138000 | github.com/janedoe", 9, False),
    ("WORK EXPERIENCE", 13, True),
    ("Acme Corp - Backend Intern 2022.06-2022.09", 10, False),
    ("- Built an ingestion pipeline in Python", 10, False),
    ("SKILLS", 13, True),
    ("Python, FastAPI, PostgreSQL, Redis, Docker", 10, False),
]

CJK_LINES = [
    ("张三", 18, True),
    ("邮箱：zhangsan@example.com 电话：13800138000", 9, False),
    ("教育经历", 14, True),
    ("某大学 计算机科学与技术 2018-2022", 10, False),
    ("项目经历", 14, True),
    ("简历优化器", 11, True),
    ("- 用 Python 实现了解析管线，支持中英混排", 10, False),
    ("技能特长", 14, True),
    ("Python、FastAPI、PostgreSQL、Docker", 10, False),
]


def test_parses_english_resume_into_context() -> None:
    parser = HybridResumeParser()

    context = parser.parse(build_pdf(ENGLISH_LINES))

    assert context.contact.email == "jane.doe@example.com"
    assert context.contact.phone == "13800138000"
    keys = [section.key for section in context.sections]
    assert "experience" in keys
    assert "skills" in keys
    assert any("Python" in skill for skill in context.skills)
    assert "warnings" in context.model_dump()


def test_parses_cjk_resume_and_keeps_text() -> None:
    parser = HybridResumeParser()

    context = parser.parse(build_pdf(CJK_LINES))

    keys = [section.key for section in context.sections]
    assert {"education", "projects", "skills"} <= set(keys)
    assert any("某大学" in section.text for section in context.sections)
    assert any("解析管线" in section.text for section in context.sections)
    assert context.projects and context.projects[0].name == "简历优化器"
    assert context.contact.email == "zhangsan@example.com"


def test_blocks_carry_size_and_page() -> None:
    blocks = extract_blocks(build_pdf(CJK_LINES))

    assert blocks
    assert all(block.page == 1 for block in blocks)
    assert max(block.size for block in blocks) > 14


def test_non_pdf_bytes_are_rejected() -> None:
    with pytest.raises(ResumeParseError) as error:
        HybridResumeParser().parse(b"this is not a pdf")

    assert error.value.code == "not_a_pdf"


def test_pdf_without_text_layer_is_rejected() -> None:
    blank = build_pdf([])

    with pytest.raises(ResumeParseError) as error:
        HybridResumeParser().parse(blank)

    assert error.value.code == "text_layer_missing"
