"""M4-T4: the TTS HTTP surface — cache hits, taxonomy errors, path safety."""

from __future__ import annotations

import asyncio
import uuid

from fastapi.testclient import TestClient

from better_resume.ai_resilience import AiUnavailable
from better_resume.main import create_app
from better_resume.media import EdgeTtsSynthesizer, TtsCache
from better_resume.settings import MediaSettings, ResilienceSettings, Settings


class FakeEngine:
    """The vendor boundary: records calls, optionally fails or stalls."""

    def __init__(
        self, *, audio: bytes = b"ID3fake", error: Exception | None = None, delay: float = 0.0
    ):
        self.audio = audio
        self.error = error
        self.delay = delay
        self.calls: list[tuple[str, str, str | None]] = []

    async def __call__(self, text: str, voice: str, rate: str | None) -> bytes:
        self.calls.append((text, voice, rate))
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error is not None:
            raise self.error
        return self.audio


def build_client(
    settings: Settings,
    tmp_path,
    engine: FakeEngine,
    *,
    resilience: ResilienceSettings | None = None,
    max_chars: int = 20,
) -> TestClient:
    media = MediaSettings(tts_storage_dir=tmp_path, tts_max_chars=max_chars, tts_voice="v1")
    overrides: dict = {"media": media}
    if resilience is not None:
        overrides["resilience"] = resilience
    app = create_app(settings.model_copy(update=overrides))
    client = TestClient(app)
    client.__enter__()
    # Same contract as llm_gateway_factory: swap the vendor engine after startup.
    app.state.tts_synthesizer = EdgeTtsSynthesizer(
        cache=TtsCache(tmp_path), engine=engine, default_voice="v1"
    )
    return client


def login(client: TestClient) -> str:
    user_id = f"tts-{uuid.uuid4().hex[:8]}"
    assert client.post("/api/v1/auth/session", json={"user_id": user_id}).status_code == 200
    return user_id


def test_tts_requires_a_session(client: TestClient) -> None:
    assert client.post("/api/v1/media/tts", json={"text": "你好"}).status_code == 401
    assert client.get("/api/v1/media/tts/" + "0" * 64 + ".mp3").status_code == 401


def test_synthesis_is_cached_and_served(settings: Settings, tmp_path) -> None:
    engine = FakeEngine()
    client = build_client(settings, tmp_path, engine)
    try:
        login(client)
        first = client.post("/api/v1/media/tts", json={"text": "第一题"})
        assert first.status_code == 200
        payload = first.json()
        assert payload["cached"] is False
        assert payload["mime_type"] == "audio/mpeg"
        assert payload["url"].endswith(f"{payload['digest']}.mp3")

        audio = client.get(payload["url"])
        assert audio.status_code == 200
        assert audio.headers["content-type"] == "audio/mpeg"
        assert audio.headers["cache-control"] == "private, max-age=86400"
        assert audio.content == b"ID3fake"

        second = client.post("/api/v1/media/tts", json={"text": "第一题"})
        assert second.json()["cached"] is True
        assert second.json()["digest"] == payload["digest"]
        assert len(engine.calls) == 1  # the vendor was asked exactly once
    finally:
        client.__exit__(None, None, None)


def test_voice_and_text_change_the_digest(settings: Settings, tmp_path) -> None:
    engine = FakeEngine()
    client = build_client(settings, tmp_path, engine)
    try:
        login(client)
        base = client.post("/api/v1/media/tts", json={"text": "同一句话"}).json()["digest"]
        other_voice = client.post(
            "/api/v1/media/tts", json={"text": "同一句话", "voice": "v2"}
        ).json()["digest"]
        other_text = client.post("/api/v1/media/tts", json={"text": "另一句话"}).json()["digest"]

        assert len({base, other_voice, other_text}) == 3
        assert [call[1] for call in engine.calls] == ["v1", "v2", "v1"]
    finally:
        client.__exit__(None, None, None)


def test_generated_audio_is_loadable_as_a_playlist(settings: Settings, tmp_path) -> None:
    """The streamed response is a normal HTTP GET (the browser Audio element needs that)."""
    engine = FakeEngine(audio=b"ID3" + b"\x00" * 32)
    client = build_client(settings, tmp_path, engine)
    try:
        login(client)
        url = client.post("/api/v1/media/tts", json={"text": "朗读"}).json()["url"]

        response = client.get(url, headers={"Range": "bytes=0-2"})

        assert response.status_code == 200
        assert response.content[:3] == b"ID3"
    finally:
        client.__exit__(None, None, None)


def test_oversized_text_is_rejected(settings: Settings, tmp_path) -> None:
    engine = FakeEngine()
    client = build_client(settings, tmp_path, engine)
    try:
        login(client)
        response = client.post("/api/v1/media/tts", json={"text": "字" * 21})

        assert response.status_code == 422
        assert "20" in response.json()["detail"]
        assert engine.calls == []
    finally:
        client.__exit__(None, None, None)


def test_unknown_or_unsafe_digest_is_404(settings: Settings, tmp_path) -> None:
    engine = FakeEngine()
    client = build_client(settings, tmp_path, engine)
    try:
        login(client)
        assert client.get("/api/v1/media/tts/" + "a" * 64 + ".mp3").status_code == 404
        # A traversal attempt never reaches the filesystem: digests are hex-only.
        assert client.get("/api/v1/media/tts/..%2F..%2Fetc%2Fpasswd.mp3").status_code == 404
        assert client.get("/api/v1/media/tts/not-a-digest.mp3").status_code == 404
    finally:
        client.__exit__(None, None, None)


def test_vendor_failure_is_503_and_writes_nothing(settings: Settings, tmp_path) -> None:
    engine = FakeEngine(error=AiUnavailable("tts vendor down", stage=_stage()))
    client = build_client(settings, tmp_path, engine)
    try:
        login(client)
        response = client.post("/api/v1/media/tts", json={"text": "会失败"})

        assert response.status_code == 503
        assert response.json()["kind"] == "unavailable"
        assert list(tmp_path.glob("*.mp3")) == []
    finally:
        client.__exit__(None, None, None)


def test_slow_vendor_hits_the_tts_deadline(settings: Settings, tmp_path) -> None:
    engine = FakeEngine(delay=0.4)
    client = build_client(
        settings, tmp_path, engine, resilience=ResilienceSettings(tts_timeout_seconds=0.05)
    )
    try:
        login(client)
        response = client.post("/api/v1/media/tts", json={"text": "很慢"})

        assert response.status_code == 504
        assert response.json()["kind"] == "timeout"
    finally:
        client.__exit__(None, None, None)


def _stage():
    from better_resume.ai_resilience import Stage

    return Stage.TTS
