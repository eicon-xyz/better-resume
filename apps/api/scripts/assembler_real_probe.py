"""P1-C: replay REAL Bailian Paraformer-realtime increments through the M4 sentence pool.

The xunfei AST adapter is the production user of AstTranscriptionAssembler, and its vendor
needs credentials this repo does not have. This probe drives the same pool with real
Paraformer increments instead: every result-generated re-sends the current sentence
(cumulative, sometimes corrected) with begin/end times — the "vendor re-sent a sentence"
shape that AstPacket(pgs=None) exists for.

It prints both sides (vendor sentences vs pool snapshots) so the evidence file can state
what the pool does with real rewrite patterns, and asserts the invariant we rely on.

Usage: uv run python scripts/assembler_real_probe.py [--wav PATH]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import uuid
import wave

from better_resume.media.adapters.paraformer_rt import derive_realtime_ws_url, open_connection
from better_resume.media.assembler import AstTranscriptionAssembler
from better_resume.media.models import AstPacket
from better_resume.settings import get_settings

DEFAULT_WAV = pathlib.Path("../../data/audio/p1c-multi-sentence-16k.wav")


def read_pcm(path: pathlib.Path) -> bytes:
    with wave.open(str(path), "rb") as handle:
        assert (handle.getnchannels(), handle.getframerate(), handle.getsampwidth()) == (
            1,
            16000,
            2,
        )
        return handle.readframes(handle.getnframes())


async def collect(settings, pcm: bytes) -> list[dict]:
    """One real vendor call; returns the raw sentence frames in arrival order."""
    ws_url = settings.media.asr_ws_url or derive_realtime_ws_url(settings.media.asr_url)
    headers = {
        "Authorization": f"Bearer {settings.dashscope_api_key}",
        "user-agent": "better-resume/p1c-assembler-probe",
    }
    task_id = uuid.uuid4().hex
    sentences: list[dict] = []
    connection = await open_connection(ws_url, headers, settings.media.asr_timeout_seconds)
    try:
        await connection.send(
            json.dumps(
                {
                    "header": {"action": "run-task", "task_id": task_id, "streaming": "duplex"},
                    "payload": {
                        "model": settings.media.asr_realtime_model,
                        "task_group": "audio",
                        "task": "asr",
                        "function": "recognition",
                        "parameters": {"format": "pcm", "sample_rate": 16000},
                        "input": {},
                    },
                }
            )
        )
        while True:
            frame = json.loads(await asyncio.wait_for(connection.recv(), timeout=15))
            if frame["header"]["event"] == "task-started":
                break
        for offset in range(0, len(pcm), 3200):
            await connection.send(pcm[offset : offset + 3200])
            while True:
                try:
                    frame = json.loads(await asyncio.wait_for(connection.recv(), timeout=0.001))
                except TimeoutError:
                    break
                _collect(frame, sentences)
        await connection.send(
            json.dumps(
                {
                    "header": {"action": "finish-task", "task_id": task_id, "streaming": "duplex"},
                    "payload": {"input": {}},
                }
            )
        )
        while True:
            frame = json.loads(await asyncio.wait_for(connection.recv(), timeout=15))
            event = _collect(frame, sentences)
            if event in ("task-finished", "task-failed"):
                break
    finally:
        await connection.close()
    return sentences


def _collect(frame: dict, sentences: list[dict]) -> str:
    event = str(frame.get("header", {}).get("event", "?"))
    if event == "result-generated":
        sentence = (frame.get("payload", {}).get("output", {}) or {}).get("sentence") or {}
        sentences.append(
            {
                "text": str(sentence.get("text") or ""),
                "begin_time": sentence.get("begin_time"),
                "end_time": sentence.get("end_time"),
                "sentence_end": bool(sentence.get("sentence_end", False)),
            }
        )
    elif event in ("task-failed", "task-finished"):
        print(f"vendor event: {event} {frame.get('header', {}).get('error_message', '')}")
    return event


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wav", type=pathlib.Path, default=DEFAULT_WAV)
    args = parser.parse_args()

    settings = get_settings()
    pcm = read_pcm(args.wav)
    print(f"audio: {args.wav.name} {len(pcm) / 32000:.1f}s")
    sentences = await collect(settings, pcm)
    archived = "".join(s["text"] for s in sentences if s["sentence_end"])
    finals = sum(sentence["sentence_end"] for sentence in sentences)
    print(f"vendor: {len(sentences)} result-generated frames, {finals} sentence_end")
    print(f"vendor archived text: {archived!r}")

    assembler = AstTranscriptionAssembler()
    print(
        "\n-- replay through AstTranscriptionAssembler (pgs=None: 'vendor re-sent a sentence') --"
    )
    for sentence in sentences:
        update = assembler.apply(
            AstPacket(
                text=sentence["text"],
                bg=sentence["begin_time"],
                ed=sentence["end_time"],
                final=sentence["sentence_end"],
            )
        )
        print(
            f"  in={sentence['text']!r:44s} end={int(sentence['sentence_end'])} "
            f"-> committed={update.committed!r} live={update.live!r}"
        )

    committed = assembler.pool.committed_text()
    display = assembler.pool.display_text()
    pooled = len(assembler.pool.ordered())
    ok = committed == archived
    print(f"\npool: sentences={pooled} (vendor produced {finals}) committed={committed!r}")
    print(f"pool: display={display!r}")
    print(f"\n{'PASS' if ok else 'FAIL'}: committed text matches the vendor's archived sentences")
    if display != archived:
        print(
            "KNOWN BOUNDARY (see P1-C-EVIDENCE.md): the pool matches by time overlap + evolves(), "
            "which does not recognise Paraformer's mid-sentence rewrites, so the live area keeps "
            f"every unmatched fragment ({pooled} pooled sentences vs {finals} real ones). No "
            "production path feeds this vendor into the pool: paraformer-rt maps replace/archive "
            "directly (P1-A) and the pool serves the xunfei AST packet shape."
        )
    print("budget note: this probe spends exactly 1 real vendor call")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
