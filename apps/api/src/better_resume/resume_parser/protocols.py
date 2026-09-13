"""ResumeParser seam: deterministic parsing, no LLM involved (D10)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .models import ResumeContext


@runtime_checkable
class ResumeParser(Protocol):
    def parse(self, pdf: bytes) -> ResumeContext:
        """pdfplumber text extraction -> section heuristics -> ResumeContext."""
        ...
