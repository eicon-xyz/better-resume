"""Request id middleware: echo or generate a request id, bind it to structlog contextvars."""

from __future__ import annotations

import uuid

import structlog
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_KEY = "request_id"


class RequestIdMiddleware:
    """Pure-ASGI middleware so it stays testable without spinning up a server."""

    def __init__(self, app: ASGIApp, header_name: str = "X-Request-Id") -> None:
        self.app = app
        self.header_name = header_name

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        inbound = MutableHeaders(scope=scope).get(self.header_name)
        request_id = inbound or uuid.uuid4().hex
        structlog.contextvars.bind_contextvars(**{REQUEST_ID_KEY: request_id})

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[self.header_name] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            structlog.contextvars.unbind_contextvars(REQUEST_ID_KEY)
