"""Load the bundled fundamentals corpus (D23).

The data ships inside the package, so the default path is anchored to this file, never to
the working directory. Missing or corrupt data is a release defect (Q19): it raises, unlike
a resume whose skills simply match nothing.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

CORPUS_FILENAME = "questions.json"
DEFAULT_CORPUS_PATH = Path(__file__).with_name(CORPUS_FILENAME)


class CorpusError(RuntimeError):
    """The bundled corpus is absent, unreadable, or does not match its schema."""


class CorpusEntry(BaseModel):
    """One reference question. topic doubles as the skill tag filtering matches on."""

    id: str = Field(min_length=1, max_length=64)
    topic: str = Field(min_length=1, max_length=32)
    question: str = Field(min_length=4, max_length=300)
    source_url: str = Field(pattern=r"^https://")
    fetched_at: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


class CorpusFile(BaseModel):
    version: Literal[1] = 1
    entries: list[CorpusEntry] = Field(min_length=1)


def load_corpus(path: Path | None = None) -> list[CorpusEntry]:
    """Read and validate the corpus; every failure names the offending file."""
    target = Path(path) if path is not None else DEFAULT_CORPUS_PATH
    try:
        raw = target.read_text(encoding="utf-8")
    except OSError as error:
        raise CorpusError(f"corpus file is missing or unreadable: {target}") from error
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise CorpusError(f"corpus file is not valid JSON: {target}") from error
    try:
        parsed = CorpusFile.model_validate(payload)
    except ValidationError as error:
        raise CorpusError(f"corpus file does not match the schema: {target}") from error
    return parsed.entries


__all__ = ["CORPUS_FILENAME", "DEFAULT_CORPUS_PATH", "CorpusEntry", "CorpusError", "load_corpus"]
