"""M3-T1: failure taxonomy — three upstream states plus the non-retryable bucket."""

from __future__ import annotations

import asyncio

from better_resume.ai_resilience import (
    AiInvalid,
    AiOverloaded,
    AiTimeout,
    AiUnavailable,
    FailureKind,
    Stage,
    classify,
    wrap,
)
from better_resume.llm_gateway import (
    FailureKind as LlmFailureKind,
)
from better_resume.llm_gateway import (
    LlmConfigError,
    LlmError,
    LlmSchemaError,
    LlmTimeoutError,
)


def test_the_three_upstream_states_are_retryable() -> None:
    for cls, kind in (
        (AiTimeout, FailureKind.TIMEOUT),
        (AiOverloaded, FailureKind.OVERLOADED),
        (AiUnavailable, FailureKind.UNAVAILABLE),
    ):
        error = cls("boom", stage=Stage.EVALUATION)
        assert error.kind is kind
        assert error.retryable is True
        assert error.cacheable is False
        assert error.stage is Stage.EVALUATION


def test_validation_failures_are_not_retryable_but_are_cacheable() -> None:
    error = AiInvalid("schema mismatch", stage=Stage.EXTRACTION)
    assert error.kind is FailureKind.INVALID
    assert error.retryable is False
    assert error.cacheable is True


def test_message_names_the_stage_and_keeps_the_cause() -> None:
    error = AiTimeout("vendor was slow", stage=Stage.FOLLOWUP)
    assert "timeout" in str(error)
    assert "followup" in str(error)
    assert "vendor was slow" in str(error)


def test_classify_routes_timeouts() -> None:
    assert classify(asyncio.TimeoutError()) is FailureKind.TIMEOUT  # noqa: UP041 - alias check
    assert classify(TimeoutError()) is FailureKind.TIMEOUT
    assert classify(LlmTimeoutError("vendor timeout")) is FailureKind.TIMEOUT


def test_classify_routes_llm_kinds() -> None:
    retryable = LlmError("vendor 500", kind=LlmFailureKind.RETRYABLE)
    assert classify(retryable) is FailureKind.UNAVAILABLE
    assert classify(LlmSchemaError("bad json")) is FailureKind.INVALID
    assert classify(LlmConfigError("no api key")) is FailureKind.INVALID


def test_classify_routes_overload_and_unknown() -> None:
    assert classify(AiOverloaded("queue full", stage=Stage.CHAT)) is FailureKind.OVERLOADED
    assert classify(ValueError("unexpected")) is FailureKind.UNAVAILABLE
    assert classify(AiUnavailable("open", stage=Stage.CHAT)) is FailureKind.UNAVAILABLE


def test_wrap_builds_the_matching_error_and_keeps_the_original() -> None:
    original = LlmTimeoutError("vendor timeout")
    wrapped = wrap(original, stage=Stage.EVALUATION)
    assert isinstance(wrapped, AiTimeout)
    assert wrapped.__cause__ is original

    schema = wrap(LlmSchemaError("bad json"), stage=Stage.EXTRACTION)
    assert isinstance(schema, AiInvalid)

    passthrough = wrap(AiOverloaded("busy", stage=Stage.CHAT), stage=Stage.CHAT)
    assert passthrough is not None
    assert isinstance(passthrough, AiOverloaded)

    unknown = wrap(RuntimeError("kaboom"), stage=Stage.CHAT)
    assert isinstance(unknown, AiUnavailable)
    assert "kaboom" in str(unknown)
