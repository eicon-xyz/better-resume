"""T1: contact / skills / projects extraction from section text."""

from __future__ import annotations

from better_resume.resume_parser.extractors import extract_contact, extract_projects, extract_skills
from better_resume.resume_parser.sections import DetectedSection


def test_contact_extracts_email_phone_and_links() -> None:
    text = "张三\n邮箱：zhangsan@example.com\n电话：13800138000\ngithub.com/zhangsan\n"

    contact = extract_contact(text)

    assert contact.email == "zhangsan@example.com"
    assert contact.phone == "13800138000"
    assert any("github.com/zhangsan" in link for link in contact.links)


def test_contact_recognizes_explicit_name_label() -> None:
    contact = extract_contact("姓名：李四\n电话：13900139000")

    assert contact.name == "李四"


def test_contact_falls_back_to_first_plausible_line() -> None:
    contact = extract_contact("Jane Doe\njane@example.com")

    assert contact.name == "Jane Doe"


def test_contact_ignores_section_headings_as_name() -> None:
    contact = extract_contact("教育经历\n某大学 2018-2022")

    assert contact.name is None


def test_skills_split_on_cjk_and_latin_separators() -> None:
    text = "Python、FastAPI，PostgreSQL / Redis | Docker\n消息队列（Kafka）、单元测试"

    skills = extract_skills(text)

    assert skills[:5] == ["Python", "FastAPI", "PostgreSQL", "Redis", "Docker"]
    assert "消息队列（Kafka）" in skills


def test_skills_dedupe_and_drop_noise() -> None:
    text = "Python\npython\n-" + "x" * 40

    skills = extract_skills(text)

    assert skills == ["Python"]


def test_projects_take_title_plus_bullets() -> None:
    sections = [
        DetectedSection(
            key="projects",
            title="项目经历",
            text="简历优化器\n- 用 Python 实现解析管线\n- 覆盖率 85%\n面试平台\n- 自研状态机",
        )
    ]

    projects = extract_projects(sections)

    assert [project.name for project in projects] == ["简历优化器", "面试平台"]
    assert projects[0].highlights[0].startswith("用 Python 实现解析管线")
    assert projects[1].highlights == ["自研状态机"]


def test_projects_are_empty_without_a_project_section() -> None:
    sections = [DetectedSection(key="education", title="教育经历", text="某大学")]

    assert extract_projects(sections) == []
