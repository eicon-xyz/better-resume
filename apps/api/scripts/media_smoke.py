"""M4 evidence: media pipeline smoke — transcription events + a real TTS file.

Usage:
    uv run python scripts/media_smoke.py --scripted   # no credentials needed (CI/local)
    uv run python scripts/media_smoke.py              # real xunfei AST (needs credentials)

What it proves:
  * the assembler + channel seam produce the replace/archive/final sequence from audio;
  * edge-tts really synthesizes an mp3 through the cache (size + header check);
  * with credentials, the same code path runs against the vendor (T10).
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from better_resume.media import (
    ChannelCtx,
    EdgeTtsSynthesizer,
    ScriptedTranscriptionChannel,
    TranscriptEvent,
    TtsCache,
    XunfeiAstAdapter,
    XunfeiCredentials,
)
from better_resume.settings import Settings, get_settings

FRAME = b"\x00" * 1280


class Recorder:
    def __init__(self) -> None:
        self.events: list[TranscriptEvent] = []

    async def __call__(self, event: TranscriptEvent) -> None:
        self.events.append(event)
        print(f"  event: {event.kind:8s} {event.text!r}")


def _load_env() -> None:
    from dotenv import load_dotenv

    for candidate in (Path(".env"), Path("../../.env")):
        if candidate.exists():
            load_dotenv(candidate, override=False)
    get_settings.cache_clear()


async def scripted_transcription() -> bool:
    print("== transcription (scripted adapter, same seam as the WS endpoint) ==")
    recorder = Recorder()
    channel = ScriptedTranscriptionChannel(on_event=recorder)
    await channel.start(ChannelCtx(session_id="smoke"))
    for _ in range(3):
        await channel.feed(FRAME)
    await channel.stop()
    await channel.stop()

    kinds = [event.kind for event in recorder.events]
    final = recorder.events[-1].text if recorder.events else ""
    print(f"  sequence: {kinds}")
    print(f"  final   : {final!r}")
    assert kinds == ["replace", "replace", "archive", "final"], kinds
    assert final == "我负责了订单写入链路的重构。", final
    return True


async def xunfei_transcription(settings: Settings) -> bool:
    print("== transcription (real xunfei AST) ==")
    credentials = XunfeiCredentials(
        app_id=settings.xunfei_app_id,
        access_key_id=settings.xunfei_access_key_id,
        access_key_secret=settings.xunfei_access_key_secret,
    )
    try:
        credentials.require()
    except Exception as exc:  # noqa: BLE001
        print(f"  SKIPPED: {exc}")
        print("  set BR_XUNFEI_APP_ID / BR_XUNFEI_ACCESS_KEY_ID / BR_XUNFEI_ACCESS_KEY_SECRET")
        return False

    recorder = Recorder()
    adapter = XunfeiAstAdapter(credentials=credentials, on_event=recorder)
    await adapter.start(ChannelCtx(session_id="smoke"))
    print("  connected; feeding 2 s of silence (real speech needs a microphone, see T10)")
    for _ in range(50):
        await adapter.feed(FRAME)
        await asyncio.sleep(0.04)
    await adapter.stop()
    print(f"  events: {len(recorder.events)}")
    return True


async def tts_once(settings: Settings) -> bool:
    print("== tts (real edge-tts through the cache) ==")
    cache = TtsCache(settings.media.tts_storage_dir)
    synthesizer = EdgeTtsSynthesizer(cache=cache, default_voice=settings.media.tts_voice)
    text = "欢迎参加模拟面试，请先介绍一下你自己。"
    try:
        reference = await synthesizer.synthesize(text)
    except Exception as exc:  # noqa: BLE001
        print(f"  FAILED: {type(exc).__name__}: {exc}")
        return False

    audio = cache.read(synthesizer.cache_key(text)) or b""
    print(f"  voice : {settings.media.tts_voice}")
    print(f"  bytes : {len(audio)}")
    print(f"  header: {audio[:4]!r}")
    print(f"  file  : {reference.path}")
    assert len(audio) > 1000, "suspiciously small mp3"
    return True


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scripted", action="store_true", help="skip the vendor entirely")
    args = parser.parse_args()

    _load_env()
    settings = get_settings()
    print(f"adapter setting: {settings.media.transcription_adapter}")

    ok = True
    if args.scripted:
        ok &= await scripted_transcription()
    else:
        ok &= await xunfei_transcription(settings)
    ok &= await tts_once(settings)
    print("\nresult:", "ok" if ok else "incomplete (see above)")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
