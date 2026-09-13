"""Failure taxonomy for LLM calls: retryable / non-retryable / vendor (§12.2)."""

from __future__ import annotations

from enum import StrEnum


class FailureKind(StrEnum):
    RETRYABLE = "retryable"
    NON_RETRYABLE = "non_retryable"
    VENDOR = "vendor"


class LlmError(Exception):
    def __init__(self, message: str, *, kind: FailureKind, status_code: int | None = None) -> None:
        super().__init__(message)
        self.kind = kind
        self.status_code = status_code

    @property
    def retryable(self) -> bool:
        return self.kind is FailureKind.RETRYABLE


class LlmConfigError(LlmError):
    """Unknown/disabled model or missing credential: retrying cannot help."""

    def __init__(self, message: str) -> None:
        super().__init__(message, kind=FailureKind.NON_RETRYABLE)


class LlmVendorError(LlmError):
    """The vendor answered with an error status; 5xx/429 are worth retrying."""

    def __init__(self, message: str, *, status_code: int) -> None:
        retryable = status_code >= 500 or status_code == 429
        kind = FailureKind.RETRYABLE if retryable else FailureKind.VENDOR
        super().__init__(message, kind=kind, status_code=status_code)


class LlmTimeoutError(LlmError):
    def __init__(self, message: str = "llm request timed out") -> None:
        super().__init__(message, kind=FailureKind.RETRYABLE)


class LlmSchemaError(LlmError):
    """Structured output never satisfied the caller's Pydantic schema."""

    def __init__(self, message: str) -> None:
        super().__init__(message, kind=FailureKind.NON_RETRYABLE)
