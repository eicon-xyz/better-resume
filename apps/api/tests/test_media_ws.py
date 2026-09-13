"""M4-T3: the transcription WebSocket — ticket handshake, events, single channel per user."""

from __future__ import annotations

import json
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from better_resume.settings import Settings


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
