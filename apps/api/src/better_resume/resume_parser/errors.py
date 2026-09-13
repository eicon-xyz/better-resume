"""Resume parsing failures; codes are stable so the UI can explain what to do."""

from __future__ import annotations

from typing import Literal

ResumeParseErrorCode = Literal["not_a_pdf", "text_layer_missing", "unreadable"]


class ResumeParseError(Exception):
    def __init__(self, code: ResumeParseErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
