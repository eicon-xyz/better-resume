"""T2: the prompt carries canonical section keys and the filtered fundamentals corpus."""

from __future__ import annotations

from better_resume.interview_engine.categories import QuestionCategory
from better_resume.interview_engine.corpus import CorpusEntry
from better_resume.interview_engine.prompts import build_messages, render_context
from better_resume.resume_parser import ResumeContext, Section


def context() -> ResumeContext:
    return ResumeContext(
        sections=[
            Section(
                title="实习经历",
                key="internship",
                bullets=["乙公司 后端实习生 2023.06-2023.09"],
            ),
            Section(title="项目经历", key="projects", bullets=["简历优化器：把解析结果结构化"]),
        ],
        skills=["Python", "Redis"],
    )


def corpus_entry() -> CorpusEntry:
    return CorpusEntry(
        id="redis-cache-avalanche",
        topic="Redis",
        question="缓存雪崩、击穿、穿透分别是什么？各自的缓解手段是什么？",
        source_url="https://redis.io/docs/latest/",
        fetched_at="2026-10-11",
    )


def test_render_context_labels_each_section_with_its_key() -> None:
    lines = render_context(context()).splitlines()

    internship_line = next(line for line in lines if "实习经历" in line)
    project_line = next(line for line in lines if "项目经历" in line)

    assert "internship" in internship_line
    assert "projects" in project_line


def test_build_messages_includes_the_filtered_corpus() -> None:
    messages = build_messages(context(), count=5, corpus=[corpus_entry()])

    user = messages[-1].content
    assert "缓存雪崩、击穿、穿透分别是什么？" in user
    assert "Redis" in user
    assert "简历上下文" in user


def test_build_messages_without_corpus_omits_the_block() -> None:
    messages = build_messages(context(), count=5)

    user = messages[-1].content
    assert "参考题" not in user
    assert "实习经历" in user


def test_build_messages_states_the_required_mix() -> None:
    messages = build_messages(
        context(),
        count=5,
        mix={QuestionCategory.PROJECT: 2, QuestionCategory.FUNDAMENTALS: 3},
    )

    user = messages[-1].content
    mix_line = next(line for line in user.splitlines() if "配比" in line)
    assert "项目 2 道" in mix_line
    assert "八股 3 道" in mix_line
    assert "实习" not in mix_line
