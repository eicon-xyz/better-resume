"""the deploy fake vendor must satisfy the real pydantic contracts.

The compose smoke and the kill drill both point a smoke-fake model at
`apps/api/scripts/fake_openai.py`. These tests keep that fake honest: every payload it
produces is parsed by the same models the engine validates vendor output with.
"""

from __future__ import annotations

import enum
import json
import typing

from pydantic import BaseModel
from scripts.fake_openai import NO_CATEGORY_MARKER, completion_payload, scene_for

from better_resume.interview_engine.categories import QuestionCategory
from better_resume.interview_engine.evaluation import (
    LOW_SCORE_THRESHOLD,
    SCORING_SYSTEM_PROMPT,
    ScoreResult,
)
from better_resume.interview_engine.follow_up_service import (
    FOLLOW_UP_SYSTEM_PROMPT,
    FollowUpQuestion,
)
from better_resume.interview_engine.prompts import (
    SYSTEM_PROMPT,
    GeneratedQuestion,
    QuestionBatch,
)
from better_resume.interview_engine.report_service import SUMMARY_SYSTEM_PROMPT, ReportSummary


def _controlled_enum_fields(model: type[BaseModel]) -> dict[str, type[enum.Enum]]:
    """Contract fields whose value set is a controlled enum, found by reflection.

    Reflection keeps the guard honest: a newly added enum field is enforced without
    touching this test.
    """
    found: dict[str, type[enum.Enum]] = {}
    for name, field in model.model_fields.items():
        for candidate in (field.annotation, *typing.get_args(field.annotation)):
            if isinstance(candidate, type) and issubclass(candidate, enum.Enum):
                found[name] = candidate
                break
    return found


def _unusable_enum_fields(payload: object, model: type[BaseModel]) -> list[str]:
    """Which controlled enum fields this raw payload omits or fills with a foreign value.

    The payload is inspected before pydantic: a nullable field that defaults to None still
    counts as missing, and "it parses" alone must not pass for a controlled field.
    """
    problems: list[str] = []
    if not isinstance(payload, dict):
        return problems
    for name, enum_type in _controlled_enum_fields(model).items():
        legal = {member.value for member in enum_type}
        if name not in payload:
            problems.append(f"{model.__name__}.{name}: missing")
        elif payload[name] not in legal:
            problems.append(f"{model.__name__}.{name}={payload[name]!r}: not a legal value")
    for name, field in model.model_fields.items():
        if name not in payload:
            continue
        nested = [
            argument
            for argument in typing.get_args(field.annotation)
            if isinstance(argument, type) and issubclass(argument, BaseModel)
        ]
        if not nested:
            continue
        items = payload[name] if isinstance(payload[name], list) else [payload[name]]
        for item in items:
            if isinstance(item, dict):
                problems.extend(_unusable_enum_fields(item, nested[0]))
    return problems


#: Every (prompt, contract) pair the fake answers; the prompts are the real system prompts.
_VENDOR_CONTRACTS = (
    (f"{SYSTEM_PROMPT}\n请出 3 道面试题，难度由浅入深。", QuestionBatch),
    (SCORING_SYSTEM_PROMPT, ScoreResult),
    (FOLLOW_UP_SYSTEM_PROMPT, FollowUpQuestion),
    (SUMMARY_SYSTEM_PROMPT, ReportSummary),
)


def test_every_controlled_enum_field_in_the_contracts_is_filled_by_the_fake() -> None:
    """The fake must supply a legal value for every controlled enum field (D22 / D23).

    "It parses" is not enough: nullable enum fields pass validation while absent, so this
    guard checks the raw payload the engine validates.
    """
    for prompt, model in _VENDOR_CONTRACTS:
        payload = completion_payload(prompt)
        assert _unusable_enum_fields(payload, model) == []


class _Seniority(enum.StrEnum):
    """A throwaway controlled enum, only to prove the guard reacts to an unseen field."""

    JUNIOR = "junior"
    SENIOR = "senior"


class _ExtendedQuestion(GeneratedQuestion):
    """GeneratedQuestion plus one controlled enum field, for the guard's own probe test."""

    seniority: _Seniority | None = None


def test_the_guard_catches_a_controlled_enum_field_the_payload_never_mentions() -> None:
    payload = {
        "topic": "主题",
        "focus_points": ["要点"],
        "text": "请讲讲这个项目",
        "category": "project",
    }

    assert _unusable_enum_fields(payload, _ExtendedQuestion) == [
        "_ExtendedQuestion.seniority: missing"
    ]


def test_questions_carry_a_legal_category() -> None:
    payload = completion_payload(f"{SYSTEM_PROMPT}\n请出 3 道面试题，难度由浅入深。")
    legal = {category.value for category in QuestionCategory}

    assert payload["questions"]
    assert all(question["category"] in legal for question in payload["questions"])


def test_the_question_prompt_marker_selects_the_no_category_shape() -> None:
    payload = completion_payload(
        f"{SYSTEM_PROMPT}\n请出 3 道面试题，难度由浅入深。{NO_CATEGORY_MARKER}"
    )

    assert all("category" not in question for question in payload["questions"])
    batch = QuestionBatch.model_validate(payload)
    assert all(question.category is None for question in batch.questions)


def test_both_question_shapes_are_selectable_from_the_same_prompt_entry_point() -> None:
    prompt = f"{SYSTEM_PROMPT}\n请出 2 道面试题，难度由浅入深。"

    with_category = completion_payload(prompt)
    without_category = completion_payload(f"{prompt}{NO_CATEGORY_MARKER}")

    assert all("category" in question for question in with_category["questions"])
    assert all("category" not in question for question in without_category["questions"])


def test_scene_detection_follows_the_real_system_prompts() -> None:
    # The api sends no scene header, so prompt sniffing is the only signal the fake has.
    assert scene_for(SYSTEM_PROMPT) == "questions"
    assert scene_for(SCORING_SYSTEM_PROMPT) == "score"
    assert scene_for(FOLLOW_UP_SYSTEM_PROMPT) == "follow_up"
    assert scene_for(SUMMARY_SYSTEM_PROMPT) == "summary"


def test_question_batch_payload_validates() -> None:
    payload = completion_payload(f"{SYSTEM_PROMPT}\n请出 3 道面试题，难度由浅入深。")

    batch = QuestionBatch.model_validate(payload)

    assert len(batch.questions) == 3
    assert batch.resume_score == 72.0
    assert all(question.text for question in batch.questions)


def test_requested_question_count_is_respected_and_clamped() -> None:
    assert len(completion_payload("请出 5 道面试题")["questions"]) == 5
    assert len(completion_payload("请出 99 道面试题")["questions"]) == 10


def test_score_payload_validates_and_triggers_a_follow_up() -> None:
    score = ScoreResult.model_validate(completion_payload(SCORING_SYSTEM_PROMPT))

    assert score.score < LOW_SCORE_THRESHOLD  # the drill wants the follow-up path exercised
    assert score.follow_up_needed is True
    assert score.missing_points


def test_follow_up_and_summary_payloads_validate() -> None:
    follow_up = FollowUpQuestion.model_validate(completion_payload(FOLLOW_UP_SYSTEM_PROMPT))
    summary = ReportSummary.model_validate(completion_payload(SUMMARY_SYSTEM_PROMPT))

    assert follow_up.text
    assert summary.summary


def test_payload_is_json_serialisable_like_a_vendor_body() -> None:
    body = json.dumps(completion_payload(SCORING_SYSTEM_PROMPT), ensure_ascii=False)

    assert json.loads(body)["score"] == 55.0
