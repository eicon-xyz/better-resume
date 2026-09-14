"""M6-T5/T8: the deploy fake vendor must satisfy the real pydantic contracts.

The compose smoke and the kill drill both point a smoke-fake model at
`apps/api/scripts/fake_openai.py`. These tests keep that fake honest: every payload it
produces is parsed by the same models the engine validates vendor output with.
"""

from __future__ import annotations

import json

from scripts.fake_openai import completion_payload, scene_for

from better_resume.interview_engine.evaluation import (
    LOW_SCORE_THRESHOLD,
    SCORING_SYSTEM_PROMPT,
    ScoreResult,
)
from better_resume.interview_engine.follow_up_service import (
    FOLLOW_UP_SYSTEM_PROMPT,
    FollowUpQuestion,
)
from better_resume.interview_engine.prompts import SYSTEM_PROMPT, QuestionBatch
from better_resume.interview_engine.report_service import SUMMARY_SYSTEM_PROMPT, ReportSummary


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
