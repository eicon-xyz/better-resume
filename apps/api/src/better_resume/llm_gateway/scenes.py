"""Business scenes for AI calls (M5): the *what*, deliberately not the *who*.

The old project bound scenes to cloud workflows through an enum + config + resolver trio
(§4.3). We keep the idea and drop the alias guessing: a scene is a business step, and a
binding row says which adapter serves it today.
"""

from __future__ import annotations

from enum import StrEnum


class LlmScene(StrEnum):
    """One AI step of the product. Inputs/outputs are documented per scene below."""

    #: Free-form conversation: history in, streamed text out (no schema).
    CHAT = "chat"
    #: Resume context in, QuestionBatch(resume_score, questions[]) out.
    QUESTION_EXTRACTION = "question_extraction"
    #: Question + focus points + answer in, ScoreResult out.
    ANSWER_EVALUATION = "answer_evaluation"
    #: Question + answer + missing points in, FollowUpQuestion out.
    FOLLOW_UP = "follow_up"
    #: Frozen numbers in, ReportSummary out (narrative only).
    REPORT_SUMMARY = "report_summary"


SCENE_LABELS: dict[LlmScene, str] = {
    LlmScene.CHAT: "对话",
    LlmScene.QUESTION_EXTRACTION: "出题",
    LlmScene.ANSWER_EVALUATION: "答案评分",
    LlmScene.FOLLOW_UP: "追问",
    LlmScene.REPORT_SUMMARY: "报告总结",
}


class AdapterKind(StrEnum):
    """The two implementations of the LlmGateway seam (D04: both are real, neither is dead)."""

    OPENAI_COMPAT = "openai_compat"
    XINGYUN = "xingyun"


def scene_label(scene: LlmScene) -> str:
    return SCENE_LABELS.get(scene, str(scene))
