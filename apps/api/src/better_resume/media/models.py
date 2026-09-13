"""media value objects: transcript events are normalized, protocol details stay in adapters."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ChannelCtx(BaseModel):
    session_id: str
    sample_rate: int = 16000
    language: str = "zh"


class TranscriptEvent(BaseModel):
    """Normalized ASR output: replace/archive patch a sentence pool, final commits it (D06)."""

    kind: Literal["replace", "archive", "final"]
    text: str
    seg_id: str | None = None


class VoiceSpec(BaseModel):
    voice: str
    rate: str | None = None
    volume: str | None = None


class AudioRef(BaseModel):
    url: str | None = None
    path: str | None = None
    mime_type: str = "audio/mpeg"
