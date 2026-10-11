"""T7: the question mix follows the resume and the candidate's override (Q8 / Q17)."""

from __future__ import annotations

from better_resume.interview_engine.categories import InterviewType, QuestionCategory
from better_resume.interview_engine.planning import plan_questions
from better_resume.resume_parser import Project, ResumeContext, Section


def context(*, internship: bool = False, project: bool = False) -> ResumeContext:
    sections = []
    if internship:
        sections.append(
            Section(
                title="实习经历",
                key="internship",
                bullets=["乙公司 后端实习生 2023.06-2023.09"],
            )
        )
    return ResumeContext(
        sections=sections,
        projects=[Project(name="简历优化器")] if project else [],
        skills=["Python"],
    )


def test_internship_and_project_split_the_default_mix() -> None:
    plan = plan_questions(context(internship=True, project=True), count=5)

    assert plan.counts == {
        QuestionCategory.INTERNSHIP: 1,
        QuestionCategory.PROJECT: 2,
        QuestionCategory.FUNDAMENTALS: 2,
    }


def test_project_only_reserves_two_slots() -> None:
    plan = plan_questions(context(project=True), count=5)

    assert plan.counts == {
        QuestionCategory.FUNDAMENTALS: 3,
        QuestionCategory.PROJECT: 2,
        QuestionCategory.INTERNSHIP: 0,
    }


def test_a_resume_without_project_or_internship_asks_fundamentals_only() -> None:
    plan = plan_questions(context(), count=5)

    assert plan.counts == {
        QuestionCategory.FUNDAMENTALS: 5,
        QuestionCategory.PROJECT: 0,
        QuestionCategory.INTERNSHIP: 0,
    }


def test_counts_always_add_up_to_the_requested_total() -> None:
    for count in range(1, 11):
        for interview_type in InterviewType:
            plan = plan_questions(
                context(internship=True, project=True), count=count, interview_type=interview_type
            )
            assert sum(plan.counts.values()) == count
            assert all(value >= 0 for value in plan.counts.values())


def test_an_explicit_focus_reserves_three_slots() -> None:
    plan = plan_questions(context(project=True), count=5, interview_type=InterviewType.PROJECT)

    assert plan.counts == {
        QuestionCategory.FUNDAMENTALS: 2,
        QuestionCategory.PROJECT: 3,
        QuestionCategory.INTERNSHIP: 0,
    }


def test_an_explicit_focus_without_the_matching_section_gives_the_slots_to_fundamentals() -> None:
    plan = plan_questions(context(), count=5, interview_type=InterviewType.PROJECT)

    assert plan.counts == {
        QuestionCategory.FUNDAMENTALS: 5,
        QuestionCategory.PROJECT: 0,
        QuestionCategory.INTERNSHIP: 0,
    }


def test_the_fundamentals_override_asks_for_no_project_questions() -> None:
    plan = plan_questions(
        context(internship=True, project=True), count=5, interview_type=InterviewType.FUNDAMENTALS
    )

    assert plan.counts == {
        QuestionCategory.FUNDAMENTALS: 5,
        QuestionCategory.PROJECT: 0,
        QuestionCategory.INTERNSHIP: 0,
    }


def test_counts_are_ordered_for_display() -> None:
    plan = plan_questions(context(internship=True, project=True), count=5)

    assert list(plan.counts) == [
        QuestionCategory.FUNDAMENTALS,
        QuestionCategory.PROJECT,
        QuestionCategory.INTERNSHIP,
    ]
