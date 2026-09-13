"""Content-addressed TTS cache: identical text+voice collapses to one file (T4)."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path


class TtsCache:
    """Files live at tts_storage_dir/<digest>.mp3; writes are atomic (tmp + replace)."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    @staticmethod
    def key(text: str, voice: str, rate: str | None = None) -> str:
        material = f"{voice}|{rate or 'default'}|{text}"
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    def path_for(self, digest: str) -> Path:
        return self.directory / f"{digest}.mp3"

    def read(self, digest: str) -> bytes | None:
        path = self.path_for(digest)
        if not path.is_file():
            return None
        return path.read_bytes()

    def write(self, digest: str, audio: bytes) -> Path:
        if not audio:
            raise ValueError("refusing to cache an empty audio payload")
        self.directory.mkdir(parents=True, exist_ok=True)
        final = self.path_for(digest)
        temporary = final.with_suffix(".mp3.part")
        temporary.write_bytes(audio)
        os.replace(temporary, final)  # atomic: readers never see a half file
        return final
