"""Resume file storage on a local volume (Q2 decision): content-addressed, no DB blobs."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StoredResume:
    path: str
    sha256: str
    size: int


class ResumeStorage:
    """\`data/resumes/<user>/<sha256>.pdf\` — identical uploads collapse to one file."""

    def __init__(self, root: Path) -> None:
        self._root = Path(root)

    def save(self, *, user_id: str, content: bytes) -> StoredResume:
        digest = hashlib.sha256(content).hexdigest()
        directory = self._root / _safe(user_id)
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"{digest}.pdf"
        if not target.exists():
            target.write_bytes(content)
        return StoredResume(path=str(target), sha256=digest, size=len(content))

    def read(self, path: str) -> bytes:
        return Path(path).read_bytes()


def _safe(user_id: str) -> str:
    return "".join(char for char in user_id if char.isalnum() or char in "-_") or "anonymous"
