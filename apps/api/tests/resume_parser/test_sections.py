"""T1: section heuristics are pure functions over TextBlocks (no PDF needed)."""

from __future__ import annotations

from better_resume.resume_parser.pdf import TextBlock
from better_resume.resume_parser.sections import split_sections


def block(
    text: str, *, size: float = 10.0, bold: bool = False, top: float = 0.0, page: int = 1
) -> TextBlock:
    return TextBlock(text=text, size=size, bold=bold, top=top, page=page)


def test_bold_keyword_heading_starts_a_section() -> None:
    blocks = [
        block("张三", size=18, bold=True, top=10),
        block("教育经历", size=13, bold=True, top=40),
        block("某大学 计算机科学与技术 2018-2022", size=10, top=60),
        block("项目经历", size=13, bold=True, top=90),
        block("简历优化器", size=11, bold=True, top=110),
        block("- 用 Python 实现了解析管线，支持中英混排", size=10, top=130),
    ]

    sections = split_sections(blocks)

    assert [section.title for section in sections] == ["教育经历", "项目经历"]
    assert [section.key for section in sections] == ["education", "projects"]
    assert "某大学" in sections[0].text
    assert "解析管线" in sections[1].text


def test_larger_size_alone_is_enough_for_cjk_headings() -> None:
    blocks = [
        block("李四", size=16, top=10),
        block("技能特长", size=13, top=40),  # not bold, but bigger than body
        block("Python、FastAPI、PostgreSQL", size=10, top=60),
    ]

    sections = split_sections(blocks)

    assert sections[0].key == "skills"
    assert "FastAPI" in sections[0].text


def test_english_headings_are_recognized_case_insensitively() -> None:
    blocks = [
        block("Jane Doe", size=16, bold=True, top=10),
        block("WORK EXPERIENCE", size=12, bold=True, top=40),
        block("Acme Corp - Backend Intern 2022", size=10, top=60),
        block("Skills", size=12, bold=True, top=90),
        block("Python, SQL", size=10, top=110),
    ]

    sections = split_sections(blocks)

    assert [section.key for section in sections] == ["work", "skills"]


def test_internship_heading_is_not_merged_into_work() -> None:
    blocks = [
        block("王五", size=16, bold=True, top=10),
        block("实习经历", size=13, bold=True, top=40),
        block("乙公司 后端实习生 2023.06-2023.09", size=10, top=60),
    ]

    sections = split_sections(blocks)

    assert [section.key for section in sections] == ["internship"]
    assert "乙公司" in sections[0].text


def test_work_and_internship_headings_produce_two_sections() -> None:
    blocks = [
        block("赵六", size=16, bold=True, top=10),
        block("工作经历", size=13, bold=True, top=40),
        block("甲公司 后端工程师 2024.07-至今", size=10, top=60),
        block("实习经历", size=13, bold=True, top=90),
        block("乙公司 后端实习生 2023.06-2023.09", size=10, top=110),
    ]

    sections = split_sections(blocks)

    assert [section.key for section in sections] == ["work", "internship"]
    assert "甲公司" in sections[0].text
    assert "乙公司" in sections[1].text


def test_without_headings_everything_lands_in_one_section() -> None:
    blocks = [
        block("张三", size=12, top=10),
        block("会用 Python 写后端", size=10, top=30),
    ]

    sections = split_sections(blocks)

    assert len(sections) == 1
    assert sections[0].key == "other"
    assert "会用 Python 写后端" in sections[0].text


def test_sentence_containing_keyword_is_not_a_heading() -> None:
    blocks = [
        block("教育经历", size=13, bold=True, top=10),
        block("我在项目经历中负责了后端部分的全部开发工作并且写了很多测试", size=10, top=40),
    ]

    sections = split_sections(blocks)

    assert len(sections) == 1
    assert "负责了后端部分" in sections[0].text
