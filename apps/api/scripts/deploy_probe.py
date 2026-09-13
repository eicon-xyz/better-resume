"""Host-side deploy probe: everything here goes through nginx, never straight to a container.

`scripts/compose_smoke.sh` runs the subcommands against the running stack and stores the
output as the evidence for M6-T5/T8. Rest: session + model registry. SSE: the proxy must
forward frames while the response is still open (heartbeat first, then the fake vendor's
chunks). WS: the transcription socket must upgrade through the proxy.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import inspect
import json
import sys
import time
import uuid
from collections.abc import Iterator

import httpx

DEFAULT_BASE = "http://127.0.0.1:8080"


@contextlib.contextmanager
def _session(base: str) -> Iterator[httpx.Client]:
    """A logged-in client. httpx opens on the first request, so this is a context manager."""
    client = httpx.Client(base_url=base, timeout=30.0, trust_env=False)
    try:
        user_id = f"deploy-{uuid.uuid4().hex[:8]}"
        response = client.post("/api/v1/auth/session", json={"user_id": user_id})
        response.raise_for_status()
        yield client
    finally:
        client.close()


def probe_rest(base: str, *, model: str) -> int:
    with _session(base) as client:
        health = client.get("/healthz")
        health.raise_for_status()
        instance = health.headers.get("x-instance-id", "")
        models = client.get("/api/v1/models")
        models.raise_for_status()
        rows = {row["name"]: row for row in models.json()}
        fake = rows.get(model)
        print(f"healthz: {health.status_code} instance={instance}")
        print(f"models: {sorted(rows)}")
        print(f"{model}: {json.dumps(fake, ensure_ascii=False)}")
        ok = health.status_code == 200 and bool(instance) and bool(fake) and fake["configured"]
        print(f"REST {'PASS' if ok else 'FAIL'}")
        return 0 if ok else 1


def probe_sse(base: str, *, model: str, timeout: float) -> int:
    frames: list[tuple[float, str]] = []
    with _session(base) as client:
        session_id = client.post("/api/v1/chat/sessions", json={}).json()["id"]
        started = time.monotonic()
        with client.stream(
            "POST",
            f"/api/v1/chat/sessions/{session_id}/stream",
            json={"content": "部署冒烟：请流式回答", "model_ref": model},
            timeout=timeout,
        ) as response:
            content_type = response.headers.get("content-type", "")
            print(f"stream: {response.status_code} content-type={content_type}")
            for line in response.iter_lines():
                if line.strip():
                    frames.append((time.monotonic() - started, line.strip()))

    for elapsed, line in frames:
        print(f"  [{elapsed:6.2f}s] {line}")

    kinds = [
        line.split(":", 1)[1].strip() if line.startswith("event:") else "comment"
        for _elapsed, line in frames
    ]
    heartbeats = sum(1 for _elapsed, line in frames if line.startswith(":"))
    contents = kinds.count("content")
    first_delay = frames[0][0] if frames else 0.0
    span = (frames[-1][0] - first_delay) if len(frames) > 1 else 0.0
    print(
        f"frames={len(frames)} content={contents} heartbeats={heartbeats} "
        f"first_frame_at={first_delay:.2f}s stream_span={span:.2f}s"
    )
    ok = (
        response.status_code == 200
        and content_type.startswith("text/event-stream")
        and "done" in kinds
        and contents >= 1
        and span > 0.1  # frames really arrived one by one, not in one buffered blob
    )
    print(f"SSE {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


async def _ws(base: str, ticket: str, cookie: str) -> int:
    import websockets

    url = base.replace("http://", "ws://").replace("https://", "wss://")
    target = f"{url}/api/v1/media/transcribe?ticket={ticket}"
    parameters = inspect.signature(websockets.connect).parameters
    header_key = "additional_headers" if "additional_headers" in parameters else "extra_headers"
    try:
        async with websockets.connect(
            target, open_timeout=10, **{header_key: {"Cookie": cookie}}
        ) as socket:
            print(f"WS_OPEN {target.split('?')[0]}")
            try:
                frame = await asyncio.wait_for(socket.recv(), timeout=3.0)
            except TimeoutError:
                print("WS first frame: (none within 3s, handshake only)")
            else:
                print(f"WS first frame: {str(frame)[:200]}")
    except Exception as exc:  # noqa: BLE001 - the probe reports what happened
        print(f"WS_FAIL {type(exc).__name__}: {exc}")
        return 1
    print("WS PASS")
    return 0


def probe_ws(base: str) -> int:
    with _session(base) as client:
        cookie = "; ".join(f"{key}={value}" for key, value in client.cookies.items())
        ticket = client.post("/api/v1/auth/ws-ticket").json()["ticket"]
    return asyncio.run(_ws(base, ticket, cookie))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="deploy probe (through nginx)")
    parser.add_argument("command", choices=["rest", "sse", "ws"])
    parser.add_argument("--base", default=DEFAULT_BASE)
    parser.add_argument("--model", default="smoke-fake")
    parser.add_argument("--timeout", type=float, default=30.0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.command == "rest":
        return probe_rest(args.base, model=args.model)
    if args.command == "sse":
        return probe_sse(args.base, model=args.model, timeout=args.timeout)
    return probe_ws(args.base)


if __name__ == "__main__":
    sys.exit(main())
