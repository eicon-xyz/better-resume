"""Explicit M0 placeholder; pdfplumber + heuristics land with M2."""

from __future__ import annotations

from .models import ResumeContext

_REASON = "ResumeParser (pdfplumber + section heuristics) is implemented in M2."


class UnimplementedResumeParser:
    def parse(self, pdf: bytes) -> ResumeContext:
        raise NotImplementedError(_REASON)
