"""the transcription WebSocket — ticket handshake, events, single channel per user."""

from __future__ import annotations

import http.server
import json
import threading
import uuid
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from better_resume.main import create_app
from better_resume.settings import MediaSettings, Settings


def login(client: TestClient) -> str:
    user_id = f"media-{uuid.uuid4().hex[:8]}"
    assert client.post("/api/v1/auth/session", json={"user_id": user_id}).status_code == 200
    return user_id


def ticket(client: TestClient) -> str:
    response = client.post("/api/v1/auth/ws-ticket")
    assert response.status_code == 200
    return response.json()["ticket"]


def test_connecting_without_a_ticket_is_rejected(client: TestClient) -> None:
    login(client)
    with (
        pytest.raises(WebSocketDisconnect) as caught,
        client.websocket_connect("/api/v1/media/transcribe"),
    ):
        pass
    assert caught.value.code == 4401


def test_a_ticket_is_single_use(client: TestClient) -> None:
    login(client)
    one = ticket(client)

    with client.websocket_connect(f"/api/v1/media/transcribe?ticket={one}"):
        pass

    with (
        pytest.raises(WebSocketDisconnect) as caught,
        client.websocket_connect(f"/api/v1/media/transcribe?ticket={one}"),
    ):
        pass
    assert caught.value.code == 4401


def test_audio_frames_become_transcript_events(client: TestClient) -> None:
    login(client)
    with client.websocket_connect(f"/api/v1/media/transcribe?ticket={ticket(client)}") as ws:
        ws.send_bytes(b"\x00" * 1280)
        first = ws.receive_json()
        ws.send_bytes(b"\x00" * 1280)
        second = ws.receive_json()

        assert first == {"kind": "replace", "text": "我负责", "seg_id": None}
        assert second["kind"] == "replace"
        assert second["text"] == "我负责了订单写入链路的重构"


def test_final_packet_archives_the_sentence(client: TestClient) -> None:
    login(client)
    with client.websocket_connect(f"/api/v1/media/transcribe?ticket={ticket(client)}") as ws:
        for _ in range(3):
            ws.send_bytes(b"\x00" * 1280)
        kinds = [ws.receive_json()["kind"] for _ in range(3)]
        # Releasing the button is an explicit stop: the server freezes the channel,
        # flushes the tail (archive/final) and only then closes.
        ws.send_text(json.dumps({"type": "stop"}))
        final = ws.receive_json()

        assert kinds == ["replace", "replace", "archive"]
        assert final["kind"] == "final"
        assert final["text"] == "我负责了订单写入链路的重构。"
        # A clean finish is an explicit close(1000) after the tail: returning without it
        # makes clients report 1006 (abnormal) although the final transcript arrived.
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()
        assert closed.value.code == 1000


def test_second_channel_for_the_same_user_is_rejected(client: TestClient) -> None:
    login(client)
    with client.websocket_connect(f"/api/v1/media/transcribe?ticket={ticket(client)}") as first:
        with (
            pytest.raises(WebSocketDisconnect) as caught,
            client.websocket_connect(f"/api/v1/media/transcribe?ticket={ticket(client)}"),
        ):
            pass
        assert caught.value.code == 4409

        first.send_bytes(b"\x00" * 1280)
        assert first.receive_json()["kind"] == "replace"


def test_disconnect_releases_the_channel(app: FastAPI, settings: Settings) -> None:
    with TestClient(app) as client:
        login(client)
        with client.websocket_connect(f"/api/v1/media/transcribe?ticket={ticket(client)}") as ws:
            ws.send_bytes(b"\x00" * 1280)
            ws.receive_json()

    assert app.state.transcription_registry.active == set()


class _RejectingAsrVendor(http.server.BaseHTTPRequestHandler):
    """A vendor endpoint that answers like a rejected credential (any POST is an error)."""

    def do_POST(self) -> None:  # noqa: N802 - the BaseHTTPRequestHandler hook is named do_POST
        self.rfile.read(int(self.headers.get("content-length", 0)))  # drain the audio we reject
        body = b'{"error": {"message": "invalid api key"}}'
        self.send_response(401)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: object) -> None:
        return None  # the request log of a test fixture is noise


@pytest.fixture
def rejecting_asr_endpoint() -> Iterator[str]:
    """A real loopback vendor, so the failure arrives over the wire (no module is mocked)."""
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _RejectingAsrVendor)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/api/v1/services/aigc/asr"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_a_failed_channel_closes_4411(settings: Settings, rejecting_asr_endpoint: str) -> None:
    """A vendor failure must not look like a clean finish: the client sees 4411, not 1000."""
    media = MediaSettings(
        transcription_adapter="qwen-asr",
        asr_url=rejecting_asr_endpoint,
        asr_timeout_seconds=5.0,
    )
    app = create_app(settings.model_copy(update={"media": media, "dashscope_api_key": "sk-test"}))

    with TestClient(app) as client:
        login(client)
        with client.websocket_connect(f"/api/v1/media/transcribe?ticket={ticket(client)}") as ws:
            # Loud and long enough that the batch adapter really asks the vendor on release.
            ws.send_bytes(b"\x10\x27" * 8000)
            ws.send_text(json.dumps({"type": "stop"}))
            # The failed channel emits no final packet: the next frame is the close.
            with pytest.raises(WebSocketDisconnect) as caught:
                ws.receive_json()
            assert caught.value.code == 4411
