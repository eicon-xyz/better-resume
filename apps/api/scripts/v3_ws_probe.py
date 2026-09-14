"""V3: drive the browser path (WS ticket -> binary PCM -> stop) against the real ASR."""

import asyncio
import inspect
import json
import pathlib
import time
import uuid
import wave

import httpx
import websockets

BASE = "http://127.0.0.1:8080"
WAV = pathlib.Path("/root/better resume/data/audio/v3-sample-16k.wav")


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
    started = time.monotonic()
    async with websockets.connect(
        url, open_timeout=20, **{header_key: {"Cookie": cookie}}
    ) as socket:
        print("WS open (101)")
        try:
            for index, offset in enumerate(range(0, len(pcm), 3200)):
                await socket.send(pcm[offset : offset + 3200])
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
        try:
            while True:
                raw = await asyncio.wait_for(socket.recv(), timeout=20)
                if isinstance(raw, bytes):
                    continue
                frame = json.loads(raw)
                frames.append(frame)
                stamp = time.monotonic() - started
                kind, text = frame.get("kind"), frame.get("text")
                print(f"  [{stamp:5.2f}s] {kind}: {text!r}")
        except (TimeoutError, websockets.exceptions.ConnectionClosed) as exc:
            print("WS closed:", type(exc).__name__, "code=", socket.close_code)
    text = frames[-1].get("text", "") if frames else ""
    ok = bool(text)
    print(f"total {time.monotonic() - started:.2f}s, frames={len(frames)}, final={text!r}")
    print("PASS" if ok else "FAIL: no final text over the websocket")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
