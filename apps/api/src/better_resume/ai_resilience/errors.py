"""Failure taxonomy for AI calls (§4.1.4): three upstream states + a non-retryable bucket.

The old project normalised every guard failure into AI_TIMEOUT / AI_OVERLOADED /
AI_UNAVAILABLE. We keep those three and add INVALID for deterministic failures
(schema violations, missing credentials): they must not be retried, but they are the
only failures a short negative cache may replay.
"""

from __future__ import annotations

from enum import StrEnum

from ..llm_gateway import LlmError, LlmTimeoutError
from .models import Stage


class FailureKind(StrEnum):
    TIMEOUT = "timeout"
    OVERLOADED = "overloaded"
    UNAVAILABLE = "unavailable"
    INVALID = "invalid"


class AiResilienceError(Exception):
    """Base class for every failure raised by the resilience seam."""

    kind: FailureKind = FailureKind.UNAVAILABLE

    def __init__(self, message: str, *, stage: Stage) -> None:
        self.message = message
        self.stage = stage
        super().__init__(f"{self.kind.value} at stage={stage.value}: {message}")

    @property
    def retryable(self) -> bool:
        return self.kind is not FailureKind.INVALID

    @property
    def cacheable(self) -> bool:
        """Only deterministic failures may be replayed from the negative cache."""
        return not self.retryable


class AiTimeout(AiResilienceError):
    kind = FailureKind.TIMEOUT


class AiOverloaded(AiResilienceError):
    kind = FailureKind.OVERLOADED


class AiUnavailable(AiResilienceError):
    kind = FailureKind.UNAVAILABLE


class AiInvalid(AiResilienceError):
    kind = FailureKind.INVALID


def classify(exc: BaseException) -> FailureKind:
    """Map any upstream failure onto the taxonomy (order matters: specifics first)."""
    if isinstance(exc, AiResilienceError):
        return exc.kind
    if isinstance(exc, (TimeoutError, LlmTimeoutError)):
        return FailureKind.TIMEOUT
    if isinstance(exc, LlmError):
        return FailureKind.UNAVAILABLE if exc.retryable else FailureKind.INVALID
    return FailureKind.UNAVAILABLE


_BY_KIND: dict[FailureKind, type[AiResilienceError]] = {
    FailureKind.TIMEOUT: AiTimeout,
    FailureKind.OVERLOADED: AiOverloaded,
    FailureKind.UNAVAILABLE: AiUnavailable,
    FailureKind.INVALID: AiInvalid,
}


def wrap(exc: BaseException, *, stage: Stage) -> AiResilienceError:
    """Normalise an arbitrary failure, keeping the original as __cause__."""
    if isinstance(exc, AiResilienceError):
        return exc
    message = str(exc) or exc.__class__.__name__
    wrapped = _BY_KIND[classify(exc)](message, stage=stage)
    wrapped.__cause__ = exc
    return wrapped
