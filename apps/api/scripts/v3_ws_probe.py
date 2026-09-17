"""V3: drive the browser path (WS ticket -> binary PCM -> stop) against the real ASR.

P1-A: --realtime paces the PCM at 1x (like a microphone) and PASSes only when incremental
"replace" partials arrived before the final — the proof that the realtime channel streams.
"""

import asyncio
import inspect
import json
import pathlib
import sys
import time
import uuid
import wave

import httpx
import websockets

BASE = "http://127.0.0.1:8080"
WAV = pathlib.Path("/root/better resume/data/audio/v3-sample-16k.wav")
REALTIME = "--realtime" in sys.argv[1:]


def read_pcm(path: pathlib.Path) -> bytes:
    with wave.open(str(path), "rb") as handle:
        assert (handle.getnchannels(), handle.getframerate(), handle.getsampwidth()) == (
            1,
            16000,
            2,
        )
        return handle.readframes(handle.getnframes())


async def main() -> int:
    pcm = read_pcm(WAV)
    async with httpx.AsyncClient(base_url=BASE, trust_env=False, timeout=60) as client:
        await client.post("/api/v1/auth/session", json={"user_id": f"v3ws-{uuid.uuid4().hex[:6]}"})
        cookie = "; ".join(f"{k}={v}" for k, v in client.cookies.items())
        ticket = (await client.post("/api/v1/auth/ws-ticket")).json()["ticket"]

    parameters = inspect.signature(websockets.connect).parameters
    header_key = "additional_headers" if "additional_headers" in parameters else "extra_headers"
    url = f"ws://127.0.0.1:8080/api/v1/media/transcribe?ticket={ticket}"
    frames: list[dict] = []
    first_partial: dict[str, float | None] = {"at": None}
    started = time.monotonic()
    async with websockets.connect(
        url, open_timeout=20, **{header_key: {"Cookie": cookie}}
    ) as socket:
        print("WS open (101)")
        reader_done = asyncio.Event()

        async def reader() -> None:
            """Read while we send: server frames must be stamped as they ARRIVE, not
            after the send loop finishes (the client buffers frames meanwhile)."""
            try:
                while True:
                    raw = await asyncio.wait_for(socket.recv(), timeout=25)
                    if isinstance(raw, bytes):
                        continue
                    frame = json.loads(raw)
                    frames.append(frame)
                    stamp = time.monotonic() - started
                    kind, text = frame.get("kind"), frame.get("text")
                    print(f"  [{stamp:5.2f}s] {kind}: {text!r}", flush=True)
                    if kind == "replace" and first_partial["at"] is None:
                        first_partial["at"] = stamp
            except (TimeoutError, websockets.exceptions.ConnectionClosed) as exc:
                print("WS closed:", type(exc).__name__, "code=", socket.close_code)
            finally:
                reader_done.set()

        _reader_task = asyncio.create_task(reader())  # held so the task cannot be GC'd
        try:
            for index, offset in enumerate(range(0, len(pcm), 3200)):
                await socket.send(pcm[offset : offset + 3200])
                if REALTIME:
                    await asyncio.sleep(0.1)  # 1x pacing: partials arrive while "speaking"
                if index % 10 == 0:
                    print(f"  sent slice {index}", flush=True)
            print(f"sent {len(pcm)} bytes of 16k pcm ({len(pcm) / 32000:.1f}s) in 100ms slices")
            await socket.send(json.dumps({"type": "stop"}))
        except Exception as exc:  # noqa: BLE001
            code = getattr(exc, "code", None) or getattr(getattr(exc, "rcvd", None), "code", None)
            reason = getattr(exc, "reason", None) or getattr(
                getattr(exc, "rcvd", None), "reason", None
            )
            print(f"SEND FAILED: {type(exc).__name__} code={code!r} reason={reason!r}")
            return 1
        await asyncio.wait_for(reader_done.wait(), timeout=35)
    text = frames[-1].get("text", "") if frames else ""
    partials = sum(1 for frame in frames if frame.get("kind") == "replace")
    ok = bool(text) and (not REALTIME or partials > 0)
    print(f"total {time.monotonic() - started:.2f}s, frames={len(frames)}, final={text!r}")
    if REALTIME:
        print(
            f"realtime mode: replace={partials} "
            f"archive={sum(1 for f in frames if f.get('kind') == 'archive')} "
            f"first_partial={first_partial['at'] if first_partial['at'] is not None else 'N/A'}s"
        )
    print("PASS" if ok else "FAIL: no final text (or no incremental partials in --realtime)")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
