"""T4: the committed OpenAPI document matches the app (drift check as a test)."""

from __future__ import annotations

import json

from scripts.export_openapi import OUTPUT, render


def test_rendering_is_stable() -> None:
    assert render() == render()


def test_committed_openapi_json_is_up_to_date() -> None:
    assert OUTPUT.exists(), "run uv run python scripts/export_openapi.py"
    assert OUTPUT.read_text(encoding="utf-8") == render(), (
        "openapi.json drift: run uv run python scripts/export_openapi.py"
    )


def test_chat_paths_are_documented() -> None:
    schema = json.loads(render())

    assert "/api/v1/chat/sessions" in schema["paths"]
    assert "/api/v1/chat/sessions/{session_id}/stream" in schema["paths"]
    assert "/api/v1/models" in schema["paths"]
    assert "HTTPValidationError" in schema["components"]["schemas"]
