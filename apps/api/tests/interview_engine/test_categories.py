"""T5: the model proposes a category, the engine decides (D23 / Q10)."""

from __future__ import annotations

from better_resume.interview_engine.categories import (
    InterviewType,
    QuestionCategory,
    coerce_interview_type,
    decide_category,
    infer_category,
)
from better_resume.interview_engine.prompts import GeneratedQuestion
from better_resume.resume_parser import Project, ResumeContext, Section


def context() -> ResumeContext:
    return ResumeContext(
        sections=[
            Section(
                title="实习经历",
                key="internship",
                bullets=["乙公司 后端实习生 2023.06-2023.09"],
            )
        ],
        projects=[Project(name="简历优化器", highlights=["解析管线"])],
        skills=["Python"],
    )


def test_a_valid_vendor_label_is_kept() -> None:
    question = GeneratedQuestion(
        topic="Redis", category="project", focus_points=["取舍"], text="讲讲缓存怎么设计的"
    )

    assert question.category is QuestionCategory.PROJECT


def test_unknown_or_missing_vendor_label_does_not_fail_the_batch() -> None:
    stray = GeneratedQuestion(
        topic="Redis", category="backend", focus_points=["原理"], text="请说明一致性哈希的原理"
    )
    missing = GeneratedQuestion(topic="Redis", focus_points=["原理"], text="请说明一致性哈希的原理")

    assert stray.category is None
    assert missing.category is None


def test_rule_fallback_prefers_the_internship_section() -> None:
    inferred = infer_category("你在实习期间负责的订单服务是怎么拆分的？", context())

    assert inferred is QuestionCategory.INTERNSHIP


def test_rule_fallback_falls_back_to_a_project_name() -> None:
    inferred = infer_category("简历优化器的解析管线是怎么设计的？", context())

    assert inferred is QuestionCategory.PROJECT


def test_rule_fallback_defaults_to_fundamentals() -> None:
    inferred = infer_category("Redis 的持久化机制有哪些？", context())

    assert inferred is QuestionCategory.FUNDAMENTALS


def test_decide_category_prefers_a_valid_vendor_label_over_the_rules() -> None:
    decided = decide_category("fundamentals", text="你在实习期间做的项目呢？", context=context())

    assert decided is QuestionCategory.FUNDAMENTALS


def test_decide_category_falls_back_when_the_label_is_unusable() -> None:
    decided = decide_category("backend", text="Redis 的持久化机制有哪些？", context=context())

    assert decided is QuestionCategory.FUNDAMENTALS


def test_interview_type_accepts_a_known_value() -> None:
    assert coerce_interview_type("project") is InterviewType.PROJECT


def test_interview_type_falls_back_to_auto_for_anything_else() -> None:
    assert coerce_interview_type("banana") is InterviewType.AUTO
    assert coerce_interview_type(None) is InterviewType.AUTO
    assert coerce_interview_type(7) is InterviewType.AUTO


def test_interview_type_tolerates_surrounding_whitespace_and_case() -> None:
    assert coerce_interview_type("  AUTO ") is InterviewType.AUTO
