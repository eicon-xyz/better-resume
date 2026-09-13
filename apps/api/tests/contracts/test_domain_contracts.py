"""Contract smoke tests for interview-engine / resume-parser / media (§12.2 signatures)."""

from __future__ import annotations

import importlib
import inspect

import pytest
from pydantic import ValidationError

from better_resume.interview_engine import (
    AnswerTurn,
    Finished,
    FollowUp,
    InterviewEngine,
    Question,
    ResumeUpload,
    TurnResult,
    UnimplementedInterviewEngine,
)
from better_resume.media import (
    ChannelCtx,
    TranscriptEvent,
    TranscriptionChannel,
    TtsSynthesizer,
    UnimplementedTranscriptionChannel,
    UnimplementedTtsSynthesizer,
    VoiceSpec,
)
from better_resume.resume_parser import (
    ResumeContext,
    ResumeParser,
    UnimplementedResumeParser,
)

MODULES = ("interview_engine", "resume_parser", "media")


def params_of(func: object) -> list[str]:
    return list(inspect.signature(func).parameters)  # type: ignore[arg-type]


@pytest.mark.parametrize("module", MODULES)
def test_module_is_importable_from_outside(module: str) -> None:
    assert importlib.import_module(f"better_resume.{module}") is not None


def test_interview_engine_shape() -> None:
    assert isinstance(UnimplementedInterviewEngine(), InterviewEngine)
    assert params_of(InterviewEngine.start) == ["self", "user_id", "resume"]
    assert params_of(InterviewEngine.answer) == ["self", "session_id", "turn"]
    assert params_of(InterviewEngine.restore) == ["self", "session_id"]
    assert params_of(InterviewEngine.finish) == ["self", "session_id"]
    assert all(
        inspect.iscoroutinefunction(getattr(InterviewEngine, name))
        for name in ("start", "answer", "restore", "finish")
    )


def test_turn_result_next_step_union() -> None:
    turn = TurnResult(
        score=0.8,
        feedback="ok",
        missing_points=["quantify impact"],
        next=FollowUp(question_no=2, text="为什么？", missing_points=["quantify impact"]),
    )

    assert turn.next.kind == "followup"
    assert Question(question_no=1, text="自我介绍").kind == "question"
    assert Finished().kind == "finished"
    assert ResumeUpload(filename="cv.pdf", content=b"%PDF").content.startswith(b"%PDF")


def test_answer_turn_requires_idempotency_key() -> None:
    turn = AnswerTurn(request_id="req-1", question_no=2, text="我的回答")

    assert turn.request_id == "req-1"
    with pytest.raises(ValidationError):
        AnswerTurn(question_no=2, text="missing request_id")  # type: ignore[call-arg]


async def test_interview_engine_placeholder_fails_loudly() -> None:
    engine = UnimplementedInterviewEngine()
    with pytest.raises(NotImplementedError):
        await engine.start("u1", ResumeUpload(filename="cv.pdf", content=b""))


def test_resume_parser_shape() -> None:
    assert isinstance(UnimplementedResumeParser(), ResumeParser)
    assert params_of(ResumeParser.parse) == ["self", "pdf"]
    assert not inspect.iscoroutinefunction(ResumeParser.parse)

    context = ResumeContext()
    assert context.contact.name is None
    assert context.sections == []


def test_media_shape() -> None:
    assert isinstance(UnimplementedTranscriptionChannel(), TranscriptionChannel)
    assert isinstance(UnimplementedTtsSynthesizer(), TtsSynthesizer)
    assert params_of(TranscriptionChannel.start) == ["self", "ctx"]
    assert params_of(TranscriptionChannel.feed) == ["self", "pcm"]
    assert params_of(TranscriptionChannel.stop) == ["self"]
    assert params_of(TtsSynthesizer.synthesize) == ["self", "text", "voice"]

    event = TranscriptEvent(kind="replace", text="你好", seg_id="seg-1")
    assert event.kind == "replace"
    assert ChannelCtx(session_id="s1").sample_rate == 16000
    assert VoiceSpec(voice="zh-CN-XiaoxiaoNeural").rate is None


async def test_media_placeholders_fail_loudly() -> None:
    channel = UnimplementedTranscriptionChannel()
    with pytest.raises(NotImplementedError):
        await channel.start(ChannelCtx(session_id="s1"))
    with pytest.raises(NotImplementedError):
        await UnimplementedTtsSynthesizer().synthesize("hi", VoiceSpec(voice="v1"))
