"""ai-resilience value objects (§12.2, D09 drops the demeanor stage)."""

from __future__ import annotations

from enum import StrEnum


class Stage(StrEnum):
    CHAT = "chat"
    EXTRACTION = "extraction"
    EVALUATION = "evaluation"
    FOLLOWUP = "followup"
