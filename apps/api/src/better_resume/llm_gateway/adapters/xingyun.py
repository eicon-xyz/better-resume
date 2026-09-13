"""Xingyun (SparkBot) workflow adapter: the second implementation of the LlmGateway seam.

Protocol per §4.1.8: POST /workflow/v1/chat/completions with Bearer apiKey:apiSecret,
body {flow_id, uid, stream, history, parameters}, SSE frames out. The cloud owns the
prompt; we own the input mapping (T4) and the output contract (Pydantic, no aliases).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, TypeVar

import httpx
import structlog

from ..errors import LlmError, LlmSchemaError, LlmTimeoutError, LlmVendorError
from ..models import (
    ChatRequest,
    ChatResult,
    ContentDelta,
    Done,
    ReasoningDelta,
    StreamEvent,
    TokenUsage,
    VendorMeta,
)
from ..scene_mapping import inspect_for_injection, to_xingyun_payload, validate_structured
from ..scenes import LlmScene

logger = structlog.get_logger("better_resume.llm_gateway.xingyun")

T = TypeVar("T")

DEFAULT_BASE_URL = "https://xingchen-api.xf-yun.com/workflow/v1/chat/completions"
_BODY_PREVIEW = 500


class XingyunWorkflowAdapter:
    """One adapter per scene binding; the HTTP client is injectable for tests."""

    def __init__(
        self,
        *,
        scene: LlmScene,
        flow_id: str,
        api_key: str,
        api_secret: str,
        uid: str = "better-resume",
        base_url: str = DEFAULT_BASE_URL,
        client: httpx.AsyncClient | None = None,
        max_attempts: int = 3,
        backoff_base_seconds: float = 0.5,
        timeout_seconds: float = 60.0,
        schema_retries: int = 1,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if not (api_key and api_secret and flow_id):
            raise LlmSchemaError("xingyun adapter needs api_key, api_secret and flow_id")
        self._scene = scene
        self._flow_id = flow_id
        self._api_key = api_key
        self._api_secret = api_secret
        self._uid = uid
        self._base_url = base_url
        self._client = client or httpx.AsyncClient(timeout=timeout_seconds, trust_env=False)
        self._owns_client = client is None
        self._max_attempts = max(1, max_attempts)
        self._backoff_base = backoff_base_seconds
        self._schema_retries = max(0, schema_retries)
        self._sleep = sleep

    @property
    def model_name(self) -> str:
        return f"xingyun:{self._flow_id}"

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    # ---- LlmGateway -------------------------------------------------------------

    async def complete(self, req: ChatRequest) -> ChatResult:
        attempts = self._schema_retries + 1
        last_error: LlmSchemaError | None = None
        for _ in range(attempts):
            content, usage = await self._retrying(lambda: self._collect(req))
            if req.response_schema is None:
                return ChatResult(content=content, model=self.model_name, parsed=None)
            try:
                parsed = validate_structured(req.response_schema, content)
            except LlmSchemaError as exc:
                last_error = exc
                logger.warning(
                    "xingyun_schema_retry",
                    scene=self._scene.value,
                    flow_id=self._flow_id,
                    error=str(exc),
                )
                continue
            return ChatResult(content=content, model=self.model_name, parsed=parsed)
        raise last_error or LlmSchemaError("xingyun response did not match the schema")

    def stream(self, req: ChatRequest) -> AsyncIterator[StreamEvent]:
        return self._stream(req)

    # ---- internals --------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}:{self._api_secret}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }

    def _payload(self, req: ChatRequest) -> dict[str, Any]:
        inspect_for_injection(req.messages, scene=self._scene, flow_id=self._flow_id)
        return to_xingyun_payload(
            self._scene, req, flow_id=self._flow_id, uid=self._uid, stream=True
        )

    async def _backoff(self, attempt: int) -> None:
        await self._sleep(self._backoff_base * (2 ** (attempt - 1)))

    async def _retrying(self, attempt: Callable[[], Awaitable[T]]) -> T:
        last: LlmError | None = None
        for attempt_index in range(1, self._max_attempts + 1):
            try:
                return await attempt()
            except LlmError as exc:
                last = exc
                if not exc.retryable or attempt_index == self._max_attempts:
                    raise
                logger.warning(
                    "xingyun_retrying",
                    attempt=attempt_index,
                    scene=self._scene.value,
                    error=str(exc),
                )
                await self._backoff(attempt_index)
        raise last or LlmTimeoutError("xingyun call failed")

    async def _collect(self, req: ChatRequest) -> tuple[str, TokenUsage | None]:
        chunks: list[str] = []
        usage: TokenUsage | None = None
        async for event in self._stream(req):
            if isinstance(event, ContentDelta):
                chunks.append(event.text)
            elif isinstance(event, VendorMeta):
                raw = event.extra.get("usage") or {}
                if raw:
                    usage = TokenUsage(**raw)
        return "".join(chunks), usage

    async def _stream(self, req: ChatRequest) -> AsyncIterator[StreamEvent]:
        response = await self._retrying(lambda: self._open_stream(req))
        try:
            async for event in self._events(response):
                yield event
        finally:
            await response.aclose()

    async def _open_stream(self, req: ChatRequest) -> httpx.Response:
        request = self._client.build_request(
            "POST", self._base_url, json=self._payload(req), headers=self._headers()
        )
        try:
            response = await self._client.send(request, stream=True)
        except httpx.TimeoutException as exc:
            raise LlmTimeoutError(f"xingyun workflow {self._flow_id} timed out") from exc
        except httpx.HTTPError as exc:
            raise LlmVendorError(f"xingyun transport error: {exc}", status_code=0) from exc

        if response.status_code >= 400:
            try:
                body = (await response.aread()).decode(errors="replace")[:_BODY_PREVIEW]
            finally:
                await response.aclose()
            raise LlmVendorError(
                f"xingyun workflow {self._flow_id} returned {response.status_code}: {body}",
                status_code=response.status_code,
            )
        return response

    async def _events(self, response: httpx.Response) -> AsyncIterator[StreamEvent]:
        finish_reason: str | None = None
        async for raw_line in response.aiter_lines():
            line = raw_line.strip()
            if not line or line.startswith(":"):
                continue
            if not line.startswith("data:"):
                continue
            data = line[len("data:") :].strip()
            if data in ("[DONE]", ""):
                break
            try:
                frame = json.loads(data)
            except json.JSONDecodeError:
                logger.warning("xingyun_dirty_frame", flow_id=self._flow_id)
                continue

            event_name = frame.get("event")
            if event_name == "done":
                finish_reason = frame.get("finish_reason") or "stop"
                break
            if event_name not in (None, "message"):
                continue  # unknown event types are ignored, never guessed at

            content = frame.get("content")
            if isinstance(content, str) and content:
                yield ContentDelta(text=content)
            reasoning = frame.get("reasoning_content")
            if isinstance(reasoning, str) and reasoning:
                yield ReasoningDelta(text=reasoning)
            if usage := frame.get("usage"):
                yield VendorMeta(model=self.model_name, extra={"usage": usage})
            if frame.get("finish_reason"):
                finish_reason = str(frame["finish_reason"])

        yield Done(finish_reason=finish_reason)
