"""Request id middleware: echo or generate a request id, bind it to structlog contextvars."""

from __future__ import annotations

import uuid

import structlog
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_KEY = "request_id"
INSTANCE_ID_HEADER = "X-Instance-Id"

logger = structlog.get_logger("better_resume.http")


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
                logger.info(
                    "http_request",
                    method=scope.get("method"),
                    path=scope.get("path"),
                    status=message["status"],
                )
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            structlog.contextvars.unbind_contextvars(REQUEST_ID_KEY)


class InstanceIdMiddleware:
    """Stamp every response with the instance that produced it.

    nginx spreads requests over several api containers (M6-T5), so this header is how an
    operator - and the kill-an-instance drill - knows who answered.
    """

    def __init__(
        self, app: ASGIApp, instance_id: str, header_name: str = INSTANCE_ID_HEADER
    ) -> None:
        self.app = app
        self.instance_id = instance_id
        self.header_name = header_name

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_instance(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[self.header_name] = self.instance_id
            await send(message)

        await self.app(scope, receive, send_with_instance)
