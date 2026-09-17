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
import time
from pathlib import Path

from better_resume.media import (
    ChannelCtx,
    EdgeTtsSynthesizer,
    ParaformerRealtimeAdapter,
    QwenAsrFlashAdapter,
    ScriptedTranscriptionChannel,
    TranscriptEvent,
    TtsCache,
    XunfeiAstAdapter,
    XunfeiCredentials,
    derive_realtime_ws_url,
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


def read_pcm(path: Path) -> bytes:
    """Read a 16 kHz mono 16-bit WAV and hand back its raw PCM (the channel's format)."""
    import wave

    with wave.open(str(path), "rb") as handle:
        if (handle.getnchannels(), handle.getframerate(), handle.getsampwidth()) != (1, 16000, 2):
            raise SystemExit(
                f"{path} must be 16 kHz mono 16-bit WAV, got "
                f"{handle.getnchannels()}ch/"
                f"{handle.getframerate()}Hz/{handle.getsampwidth() * 8}bit"
            )
        return handle.readframes(handle.getnframes())


async def qwen_asr_transcription(settings: Settings, wav_path: Path) -> bool:
    """V3: the batch ASR channel against the real MaaS endpoint, one release per file."""
    print("== transcription (real qwen-audio-3.0-asr-flash, batch: one request per release) ==")
    pcm = read_pcm(wav_path)
    print(f"  audio: {wav_path.name} {len(pcm) / 32000:.1f}s ({len(pcm)} bytes of 16 kHz mono pcm)")
    recorder = Recorder()
    try:
        adapter = QwenAsrFlashAdapter(
            api_key=settings.dashscope_api_key,
            endpoint=settings.media.asr_url,
            model=settings.media.asr_model,
            timeout_seconds=settings.media.asr_timeout_seconds,
            on_event=recorder,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"  SKIPPED: {exc}")
        print("  set BR_DASHSCOPE_API_KEY and BR_MEDIA__ASR_URL (MaaS workspace endpoint)")
        return False

    started = time.monotonic()
    await adapter.start(ChannelCtx(session_id="smoke"))
    for offset in range(0, len(pcm), 3200):  # feed in 100 ms slices, like the browser does
        await adapter.feed(pcm[offset : offset + 3200])
    await adapter.stop()
    elapsed = time.monotonic() - started
    print(f"  request: {adapter.last_request_bytes} wav bytes, release -> text {elapsed:.2f}s")
    print(f"  events : {[event.kind for event in recorder.events]}")
    final = recorder.events[-1].text if recorder.events else ""
    print(f"  final  : {final!r}")
    if not final:
        print("  FAILED: no final text (silence, or the vendor refused)")
        return False
    return True


async def paraformer_rt_transcription(settings: Settings, wav_path: Path) -> bool:
    """P1-A: the realtime channel against the real vendor, paced at 1x like a microphone.

    Unlike the batch adapter this exercises the incremental path: partial sentences are
    expected to arrive while the audio is still being fed.
    """
    print(f"== transcription (real {settings.media.asr_realtime_model}, realtime WS) ==")
    pcm = read_pcm(wav_path)
    print(f"  audio: {wav_path.name} {len(pcm) / 32000:.1f}s ({len(pcm)} bytes of 16 kHz mono pcm)")
    recorder = Recorder()
    ws_url = settings.media.asr_ws_url or derive_realtime_ws_url(settings.media.asr_url)
    try:
        adapter = ParaformerRealtimeAdapter(
            api_key=settings.dashscope_api_key,
            ws_url=ws_url,
            model=settings.media.asr_realtime_model,
            timeout_seconds=settings.media.asr_timeout_seconds,
            on_event=recorder,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"  SKIPPED: {exc}")
        print("  set BR_DASHSCOPE_API_KEY and BR_MEDIA__ASR_URL (or BR_MEDIA__ASR_WS_URL)")
        return False

    started = time.monotonic()
    first_partial: float | None = None
    await adapter.start(ChannelCtx(session_id="smoke"))
    for offset in range(0, len(pcm), 3200):  # 1x pacing: partials arrive while "speaking"
        await adapter.feed(pcm[offset : offset + 3200])
        if first_partial is None and any(e.kind == "replace" for e in recorder.events):
            first_partial = time.monotonic() - started
        await asyncio.sleep(0.1)
    await adapter.stop()
    elapsed = time.monotonic() - started
    kinds = [event.kind for event in recorder.events]
    first = f"{first_partial:.2f}s" if first_partial is not None else "N/A"
    print(f"  streamed at 1x in {elapsed:.2f}s; first partial at {first}")
    print(
        f"  events : replace={kinds.count('replace')} "
        f"archive={kinds.count('archive')} final={kinds.count('final')}"
    )
    final = recorder.events[-1].text if recorder.events else ""
    print(f"  final  : {final!r}")
    if not final:
        print("  FAILED: no final text (silence, or the vendor refused)")
        return False
    if not kinds.count("replace"):
        print("  FAILED: no incremental replace events (realtime must stream partials)")
        return False
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
    parser.add_argument(
        "--qwen-asr-real",
        action="store_true",
        help="V3: run the batch ASR channel against the real Bailian endpoint",
    )
    parser.add_argument(
        "--paraformer-rt-real",
        action="store_true",
        help="P1-A: run the realtime ASR channel against the real Bailian endpoint",
    )
    parser.add_argument(
        "--wav", type=Path, help="16 kHz mono WAV for --qwen-asr-real / --paraformer-rt-real"
    )
    args = parser.parse_args()
    if (args.qwen_asr_real or args.paraformer_rt_real) and args.wav is None:
        parser.error("--qwen-asr-real / --paraformer-rt-real need --wav PATH")

    _load_env()
    settings = get_settings()
    print(f"adapter setting: {settings.media.transcription_adapter}")

    ok = True
    if args.scripted:
        ok &= await scripted_transcription()
    elif args.qwen_asr_real:
        ok &= await qwen_asr_transcription(settings, args.wav)
    elif args.paraformer_rt_real:
        ok &= await paraformer_rt_transcription(settings, args.wav)
    else:
        ok &= await xunfei_transcription(settings)
    ok &= await tts_once(settings)
    print("\nresult:", "ok" if ok else "incomplete (see above)")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
