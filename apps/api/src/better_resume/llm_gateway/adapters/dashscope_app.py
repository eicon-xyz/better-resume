"""P3: DashScope application-call adapter — the third implementation of the LlmGateway seam.

Protocol (Model Studio "call applications", verified 2026-09-17): `POST
{base}/api/v1/apps/{app_id}/completion` with `Authorization: Bearer <key>`; the header
`X-DashScope-SSE: enable` turns the answer into SSE frames carrying the same envelope as the
batch call. The cloud **application owns the prompt** — we own exactly two things: the input
mapping (`input.prompt` / `input.session_id`) and the output contract (Pydantic, no alias
guessing). Which app serves which scene is the binding row's job (`target_ref` = app_id).
"""

from __future__ import annotations

import asyncio
import json
import re
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
from ..scene_mapping import inspect_for_injection, to_dashscope_app_payload, validate_structured
from ..scenes import LlmScene

logger = structlog.get_logger("better_resume.llm_gateway.dashscope_app")

DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com"
_BODY_PREVIEW = 500
#: The vendor sends the literal string "null" while the answer is still streaming.
_STREAMING_FINISH = {"", "null", "none"}
#: Comment line the vendor writes before each frame: ":HTTP_STATUS/400".
_STATUS_COMMENT = re.compile(r"^:HTTP_STATUS/(\d{3})$")

T = TypeVar("T")


def _usage_from_frame(raw: Any) -> TokenUsage | None:
    """Map `usage.models[0]` onto our TokenUsage; unknown shapes are reported as absent."""
    if not isinstance(raw, dict):
        return None
    models = raw.get("models")
    if not isinstance(models, list) or not models:
        return None
    entry = models[0]
    if not isinstance(entry, dict):
        return None
    prompt = entry.get("input_tokens")
    completion = entry.get("output_tokens")
    total = None
    if isinstance(prompt, int) and isinstance(completion, int):
        total = prompt + completion
    return TokenUsage(
        prompt_tokens=prompt if isinstance(prompt, int) else None,
        completion_tokens=completion if isinstance(completion, int) else None,
        total_tokens=total,
    )


class DashScopeAppAdapter:
    """One adapter per scene binding; the HTTP client is injectable for tests."""

    def __init__(
        self,
        *,
        scene: LlmScene,
        app_id: str,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        client: httpx.AsyncClient | None = None,
        max_attempts: int = 3,
        backoff_base_seconds: float = 0.5,
        timeout_seconds: float = 60.0,
        schema_retries: int = 1,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if not (app_id and api_key):
            raise LlmSchemaError("dashscope app adapter needs app_id and api_key")
        self._scene = scene
        self._app_id = app_id
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.AsyncClient(timeout=timeout_seconds, trust_env=False)
        self._owns_client = client is None
        self._max_attempts = max(1, max_attempts)
        self._backoff_base = backoff_base_seconds
        self._schema_retries = max(0, schema_retries)
        self._sleep = sleep

    @property
    def model_name(self) -> str:
        return f"dashscope-app:{self._app_id}"

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    # ---- LlmGateway -------------------------------------------------------------

    async def complete(self, req: ChatRequest) -> ChatResult:
        attempts = self._schema_retries + 1
        last_error: LlmSchemaError | None = None
        for _ in range(attempts):
            # One retry boundary per call: _stream() already retries opening the connection,
            # and retrying a half-consumed stream would double-count attempts.
            content, usage = await self._collect(req)
            if req.response_schema is None:
                return ChatResult(content=content, model=self.model_name, usage=usage, parsed=None)
            try:
                parsed = validate_structured(req.response_schema, content)
            except LlmSchemaError as exc:
                last_error = exc
                logger.warning(
                    "dashscope_app_schema_retry",
                    scene=self._scene.value,
                    app_id=self._app_id,
                    error=str(exc),
                )
                continue
            return ChatResult(content=content, model=self.model_name, usage=usage, parsed=parsed)
        raise last_error or LlmSchemaError("dashscope app response did not match the schema")

    def stream(self, req: ChatRequest) -> AsyncIterator[StreamEvent]:
        return self._stream(req)

    # ---- internals --------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "X-DashScope-SSE": "enable",
        }

    def _payload(self, req: ChatRequest) -> dict[str, Any]:
        inspect_for_injection(req.messages, scene=self._scene, flow_id=self._app_id)
        session_id = req.vendor_ctx.workflow_id if req.vendor_ctx is not None else None
        return to_dashscope_app_payload(req, app_id=self._app_id, session_id=session_id)

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
                    "dashscope_app_retrying",
                    attempt=attempt_index,
                    scene=self._scene.value,
                    error=str(exc),
                )
                await self._backoff(attempt_index)
        raise last or LlmTimeoutError("dashscope app call failed")

    async def _collect(self, req: ChatRequest) -> tuple[str, TokenUsage | None]:
        chunks: list[str] = []
        usage: TokenUsage | None = None
        async for event in self._stream(req):
            if isinstance(event, ContentDelta):
                chunks.append(event.text)
            elif isinstance(event, VendorMeta):
                reported = _usage_from_frame(event.extra.get("usage"))
                if reported is not None:
                    usage = reported
        return "".join(chunks), usage

    async def _stream(self, req: ChatRequest) -> AsyncIterator[StreamEvent]:
        response = await self._retrying(lambda: self._open_stream(req))
        try:
            async for event in self._events(response):
                yield event
        finally:
            await response.aclose()

    async def _open_stream(self, req: ChatRequest) -> httpx.Response:
        url = f"{self._base_url}/api/v1/apps/{self._app_id}/completion"
        request = self._client.build_request(
            "POST", url, json=self._payload(req), headers=self._headers()
        )
        try:
            response = await self._client.send(request, stream=True)
        except httpx.TimeoutException as exc:
            raise LlmTimeoutError(f"dashscope app {self._app_id} timed out") from exc
        except httpx.HTTPError as exc:
            raise LlmVendorError(f"dashscope app transport error: {exc}", status_code=0) from exc

        if response.status_code >= 400:
            try:
                body = (await response.aread()).decode(errors="replace")[:_BODY_PREVIEW]
            finally:
                await response.aclose()
            raise LlmVendorError(
                f"dashscope app {self._app_id} returned {response.status_code}: {body}",
                status_code=response.status_code,
            )
        return response

    async def _events(self, response: httpx.Response) -> AsyncIterator[StreamEvent]:
        finish_reason: str | None = None
        reported_status: int | None = None
        async for raw_line in response.aiter_lines():
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith(":"):
                # The vendor reports the effective status as a comment line before each frame.
                frame_status = _STATUS_COMMENT.match(line)
                if frame_status:
                    reported_status = int(frame_status.group(1))
                continue
            if not line.startswith("data:"):
                continue
            data = line[len("data:") :].strip()
            if data in ("[DONE]", ""):
                break
            try:
                frame = json.loads(data)
            except json.JSONDecodeError:
                logger.warning("dashscope_app_dirty_frame", app_id=self._app_id)
                continue
            if not isinstance(frame, dict):
                continue

            # Real endpoint, 2026-09-17: failures arrive as HTTP 200 + an error frame. Reading
            # that as an empty answer would hide a broken binding behind a blank reply, so an
            # in-band error is raised with the status the vendor itself reported.
            code = frame.get("code")
            if isinstance(code, str) and code:
                message = str(frame.get("message", ""))[:200]
                raise LlmVendorError(
                    f"dashscope app {self._app_id} returned {code}: {message}",
                    status_code=reported_status or 400,
                )

            output = frame.get("output")
            if not isinstance(output, dict):
                output = {}
            text = output.get("text")
            if isinstance(text, str) and text:
                yield ContentDelta(text=text)
            thoughts = output.get("thoughts")
            if isinstance(thoughts, str) and thoughts:
                yield ReasoningDelta(text=thoughts)
            if usage := frame.get("usage"):
                yield VendorMeta(model=self.model_name, extra={"usage": usage})

            reported = output.get("finish_reason")
            if isinstance(reported, str) and reported.lower() not in _STREAMING_FINISH:
                finish_reason = reported
                break

        yield Done(finish_reason=finish_reason or "stop")
