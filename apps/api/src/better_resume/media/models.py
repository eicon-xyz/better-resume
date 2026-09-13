"""media value objects: transcript events are normalized, protocol details stay in adapters."""

from __future__ import annotations

from enum import StrEnum
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


class PgsKind(StrEnum):
    """xunfei AST packet generation strategy: apd appends, rpl rewrites an interval."""

    APPEND = "apd"
    REPLACE = "rpl"


class AstPacket(BaseModel):
    """One incremental packet from the vendor (the only place these fields exist)."""

    text: str = ""
    seg_id: int | None = None
    pgs: PgsKind | None = None
    rg: tuple[int, int] | None = None
    bg: int | None = None
    ed: int | None = None
    final: bool = False


class Sentence(BaseModel):
    seg_id: int
    text: str = ""
    bg: int | None = None
    ed: int | None = None
    committed: bool = False


class TranscriptUpdate(BaseModel):
    """Three-level snapshot (§4.4): committed sentences, the live tail, and the merged view."""

    full: str
    display: str
    committed: str
    live: str
    revision: int
    segment_id: int | None = None
    final_packet: bool = False
    changed: bool = False


class VoiceSpec(BaseModel):
    voice: str
    rate: str | None = None
    volume: str | None = None


class AudioRef(BaseModel):
    url: str | None = None
    path: str | None = None
    mime_type: str = "audio/mpeg"
