"""Reusable PDF fixture builder for interview-engine tests (delegates to the resume helper)."""

from __future__ import annotations

from tests.resume_parser.conftest import build_pdf

RESUME_LINES = [
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


def build_resume_pdf() -> bytes:
    return build_pdf(RESUME_LINES)
