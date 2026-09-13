"""LlmGateway seam: the single entry point for every model call (§12.2)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from .models import ChatRequest, ChatResult, StreamEvent


@runtime_checkable
class LlmGateway(Protocol):
    async def complete(self, req: ChatRequest) -> ChatResult: ...

    def stream(self, req: ChatRequest) -> AsyncIterator[StreamEvent]:
        """Yield ContentDelta / ReasoningDelta / Done / VendorMeta events."""
        ...
