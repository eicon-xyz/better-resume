from __future__ import annotations

import structlog
from starlette.types import Message, Receive, Scope, Send

from better_resume.observability.middleware import RequestIdMiddleware


async def test_inbound_request_id_is_bound_echoed_and_unbound() -> None:
    captured: dict[str, object] = {}

    async def inner(scope: Scope, receive: Receive, send: Send) -> None:
        captured["ctx"] = structlog.contextvars.get_contextvars()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    sent: list[Message] = []

    async def send(message: Message) -> None:
        sent.append(message)

    async def receive() -> Message:
        return {"type": "http.request"}

    middleware = RequestIdMiddleware(inner, header_name="X-Request-Id")
    scope: Scope = {"type": "http", "headers": [(b"x-request-id", b"trace-123")]}

    await middleware(scope, receive, send)

    assert captured["ctx"] == {"request_id": "trace-123"}
    assert dict(sent[0]["headers"])[b"x-request-id"] == b"trace-123"
    assert structlog.contextvars.get_contextvars() == {}


async def test_missing_request_id_is_generated() -> None:
    captured: dict[str, object] = {}

    async def inner(scope: Scope, receive: Receive, send: Send) -> None:
        captured["ctx"] = structlog.contextvars.get_contextvars()
        await send({"type": "http.response.start", "status": 200, "headers": []})

    async def send(message: Message) -> None:
        return None

    async def receive() -> Message:
        return {"type": "http.request"}

    middleware = RequestIdMiddleware(inner)
    await middleware({"type": "http", "headers": []}, receive, send)

    request_id = captured["ctx"]["request_id"]  # type: ignore[index]
    assert isinstance(request_id, str)
    assert len(request_id) == 32


async def test_non_http_scopes_pass_through() -> None:
    seen: list[str] = []

    async def inner(scope: Scope, receive: Receive, send: Send) -> None:
        seen.append(scope["type"])

    async def send(message: Message) -> None:
        return None

    async def receive() -> Message:
        return {"type": "lifespan.startup"}

    middleware = RequestIdMiddleware(inner)
    await middleware({"type": "lifespan"}, receive, send)

    assert seen == ["lifespan"]
