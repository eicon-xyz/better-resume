"""M4-T4: TTS cache and the edge-tts adapter (the vendor engine is injected)."""

from __future__ import annotations

import pytest

from better_resume.ai_resilience import AiUnavailable
from better_resume.media import EdgeTtsSynthesizer, TtsCache, VoiceSpec


class FakeEngine:
    def __init__(self, audio: bytes = b"ID3fake-mp3-bytes") -> None:
        self.audio = audio
        self.calls: list[tuple[str, str, str | None]] = []

    async def __call__(self, text: str, voice: str, rate: str | None) -> bytes:
        self.calls.append((text, voice, rate))
        return self.audio


def test_cache_keys_are_content_addressed(tmp_path) -> None:
    cache = TtsCache(tmp_path)

    first = cache.key("你好", "zh-CN-XiaoxiaoNeural")
    assert first == cache.key("你好", "zh-CN-XiaoxiaoNeural")
    assert first != cache.key("你好", "zh-CN-YunxiNeural")
    assert first != cache.key("你好", "zh-CN-XiaoxiaoNeural", rate="+20%")
    assert first != cache.key("再见", "zh-CN-XiaoxiaoNeural")


def test_cache_write_is_atomic_and_round_trips(tmp_path) -> None:
    cache = TtsCache(tmp_path)
    digest = cache.key("你好", "v")

    path = cache.write(digest, b"audio")

    assert path.read_bytes() == b"audio"
    assert cache.read(digest) == b"audio"
    assert list(tmp_path.glob("*.part")) == []
    assert cache.read("0" * 64) is None


def test_cache_refuses_empty_payloads(tmp_path) -> None:
    with pytest.raises(ValueError):
        TtsCache(tmp_path).write("a" * 64, b"")


async def test_synthesize_writes_once_and_reuses_the_cache(tmp_path) -> None:
    engine = FakeEngine()
    synthesizer = EdgeTtsSynthesizer(cache=TtsCache(tmp_path), engine=engine, default_voice="v1")

    first = await synthesizer.synthesize("你好")
    second = await synthesizer.synthesize("你好")

    assert engine.calls == [("你好", "v1", None)]
    assert first.url == second.url
    assert first.mime_type == "audio/mpeg"
    assert first.path is not None and first.path.endswith(".mp3")
    assert synthesizer.cached("你好") == b"ID3fake-mp3-bytes"


async def test_different_voices_synthesize_separately(tmp_path) -> None:
    engine = FakeEngine()
    synthesizer = EdgeTtsSynthesizer(cache=TtsCache(tmp_path), engine=engine, default_voice="v1")

    await synthesizer.synthesize("你好", VoiceSpec(voice="v2"))
    await synthesizer.synthesize("你好", VoiceSpec(voice="v2"))
    await synthesizer.synthesize("你好")

    assert [call[1] for call in engine.calls] == ["v2", "v1"]


async def test_empty_audio_is_an_unavailable_error(tmp_path) -> None:
    synthesizer = EdgeTtsSynthesizer(cache=TtsCache(tmp_path), engine=FakeEngine(audio=b""))

    with pytest.raises(AiUnavailable, match="no audio"):
        await synthesizer.synthesize("你好")

    assert synthesizer.cached("你好") is None
