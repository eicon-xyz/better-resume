"""Explicit M0 placeholder; adapters (OpenAICompat / Xingyun) land with M1/M5."""

from __future__ import annotations

from collections.abc import AsyncIterator

from .models import ChatRequest, ChatResult, StreamEvent

_REASON = "LlmGateway adapters are implemented in M1 (OpenAI-compatible) / M5 (Xingyun)."


class UnimplementedLlmGateway:
    async def complete(self, req: ChatRequest) -> ChatResult:
        raise NotImplementedError(_REASON)

    def stream(self, req: ChatRequest) -> AsyncIterator[StreamEvent]:
        raise NotImplementedError(_REASON)
