"""OpenAI-compatible adapter (DeepSeek and friends): one complete(), one stream().

Everything vendor-specific lives here: payload shape, SSE frames, reasoning_content
normalization, retries/timeouts, token accounting. Failures are classified (§12.2).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from typing import Any, TypeVar

import httpx
import structlog

from ..errors import LlmError, LlmSchemaError, LlmTimeoutError, LlmVendorError
from ..firewall import harden_system_prompt, inspect_prompt
from ..models import (
    ChatRequest,
    ChatResult,
    ContentDelta,
    Done,
    ModelSpec,
    ReasoningDelta,
    StreamEvent,
    TokenUsage,
    VendorMeta,
)

logger = structlog.get_logger("better_resume.llm_gateway")

T = TypeVar("T")

_BODY_PREVIEW = 500


class OpenAICompatAdapter:
    """`/chat/completions` over HTTP; the client is injectable so tests never hit the network."""

    def __init__(
        self,
        spec: ModelSpec,
        *,
        api_key: str,
        client: httpx.AsyncClient | None = None,
        max_attempts: int = 3,
        backoff_base_seconds: float = 0.5,
        timeout_seconds: float = 60.0,
        schema_retries: int = 1,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._spec = spec
        self._api_key = api_key
        self._client = client or _build_client(timeout_seconds)
        self._owns_client = client is None
        self._max_attempts = max(1, max_attempts)
        self._backoff_base = backoff_base_seconds
        self._schema_retries = max(0, schema_retries)
        self._sleep = sleep

    # ---- public API -------------------------------------------------------------

    async def complete(self, req: ChatRequest) -> ChatResult:
        attempts = self._schema_retries + 1 if req.response_schema is not None else 1
        schema_error: LlmSchemaError | None = None

        for _ in range(attempts):
            result = await self._retrying(lambda: self._complete_once(req))
            if req.response_schema is None:
                return result
            try:
                parsed = self._validate(req.response_schema, result.content)
            except LlmSchemaError as exc:
                schema_error = exc
                logger.warning("llm_schema_invalid", model=self._spec.name, error=str(exc))
                continue
            return result.model_copy(update={"parsed": parsed})

        raise schema_error or LlmSchemaError("structured output failed validation")

    def stream(self, req: ChatRequest) -> AsyncIterator[StreamEvent]:
        return self._stream(req)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    # ---- internals --------------------------------------------------------------

    def _url(self) -> str:
        return f"{self._spec.base_url.rstrip('/')}/chat/completions"

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}

    def _messages(self, req: ChatRequest) -> list[dict[str, str]]:
        system_prompt = self._spec.system_prompt
        for message in req.messages:
            if message.role == "user":
                verdict = inspect_prompt(message.content)
                if verdict.blocked:
                    logger.warning(
                        "llm_prompt_injection_suspected",
                        model=self._spec.name,
                        patterns=verdict.matched,
                    )

        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": harden_system_prompt(system_prompt)})
        messages.extend({"role": m.role, "content": m.content} for m in req.messages)
        return messages

    def _payload(self, req: ChatRequest, *, stream: bool) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": req.model_ref or self._spec.model_id,
            "messages": self._messages(req),
            "max_tokens": req.max_tokens or self._spec.max_tokens,
            "temperature": req.temperature
            if req.temperature is not None
            else self._spec.temperature,
        }
        if stream:
            payload["stream"] = True
        elif req.response_schema is not None:
            payload["response_format"] = {"type": "json_object"}
        return payload

    def _backoff(self, attempt: int) -> float:
        return self._backoff_base * (2 ** (attempt - 1))

    async def _retrying(self, attempt: Callable[[], Awaitable[T]]) -> T:
        last: LlmError | None = None
        for attempt_index in range(1, self._max_attempts + 1):
            try:
                return await attempt()
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last = LlmTimeoutError(str(exc) or exc.__class__.__name__)
            except LlmError as exc:
                if not exc.retryable:
                    raise
                last = exc
            if attempt_index < self._max_attempts:
                await self._sleep(self._backoff(attempt_index))
        assert last is not None
        raise last

    async def _complete_once(self, req: ChatRequest) -> ChatResult:
        response = await self._client.post(
            self._url(), json=self._payload(req, stream=False), headers=self._headers()
        )
        self._raise_for_status(response)
        body = response.json()
        message = (body.get("choices") or [{}])[0].get("message") or {}
        return ChatResult(
            content=message.get("content") or "",
            reasoning=message.get("reasoning_content"),
            model=body.get("model") or self._spec.model_id,
            usage=_usage(body.get("usage")),
            raw_response=body if self._spec.extra.get("keep_raw") else None,
        )

    async def _stream(self, req: ChatRequest) -> AsyncIterator[StreamEvent]:
        response = await self._retrying(lambda: self._open_stream(req))
        try:
            async for event in self._events(response):
                yield event
        finally:
            await response.aclose()

    async def _open_stream(self, req: ChatRequest) -> httpx.Response:
        request = self._client.build_request(
            "POST", self._url(), json=self._payload(req, stream=True), headers=self._headers()
        )
        response = await self._client.send(request, stream=True)
        if response.status_code >= 400:
            try:
                body = (await response.aread()).decode(errors="replace")[:_BODY_PREVIEW]
            finally:
                await response.aclose()
            raise LlmVendorError(
                f"vendor returned {response.status_code}: {body}", status_code=response.status_code
            )
        return response

    async def _events(self, response: httpx.Response) -> AsyncIterator[StreamEvent]:
        finish_reason: str | None = None
        async for raw_line in response.aiter_lines():
            line = raw_line.strip()
            if not line or line.startswith(":"):
                continue  # heartbeat / blank keep-alive frame
            if not line.startswith("data:"):
                continue
            data = line[len("data:") :].strip()
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                logger.warning("llm_stream_dirty_frame", model=self._spec.name)
                continue

            choices = chunk.get("choices") or []
            if choices:
                choice = choices[0]
                delta = choice.get("delta") or {}
                if content := delta.get("content"):
                    yield ContentDelta(text=content)
                if reasoning := delta.get("reasoning_content"):
                    yield ReasoningDelta(text=reasoning)
                finish_reason = choice.get("finish_reason") or finish_reason
            if usage := chunk.get("usage"):
                yield VendorMeta(model=chunk.get("model"), extra={"usage": usage})

        yield Done(finish_reason=finish_reason)

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.status_code >= 400:
            raise LlmVendorError(
                f"vendor returned {response.status_code}: {response.text[:_BODY_PREVIEW]}",
                status_code=response.status_code,
            )

    @staticmethod
    def _validate(schema: type[Any], content: str) -> Any:
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise LlmSchemaError(f"response is not valid JSON: {exc}") from exc

        from pydantic import ValidationError

        try:
            return schema.model_validate(payload)
        except ValidationError as exc:
            raise LlmSchemaError(f"response does not match {schema.__name__}: {exc}") from exc


def _build_client(timeout_seconds: float) -> httpx.AsyncClient:
    """Build the HTTP client without dying on a malformed proxy environment.

    httpx parses NO_PROXY eagerly and raises InvalidURL for entries like a bare IPv6
    address ("::1"), which some WSL setups export. Failing back to `trust_env=False`
    keeps the service alive (and logs why) instead of breaking every request.
    """
    timeout = httpx.Timeout(timeout_seconds)
    try:
        return httpx.AsyncClient(timeout=timeout)
    except (httpx.InvalidURL, ValueError):
        logger.warning("llm_client_proxy_env_ignored", reason="malformed NO_PROXY")
        return httpx.AsyncClient(timeout=timeout, trust_env=False)


def _usage(raw: Mapping[str, Any] | None) -> TokenUsage | None:
    if not raw:
        return None
    details = raw.get("completion_tokens_details") or {}
    return TokenUsage(
        prompt_tokens=raw.get("prompt_tokens"),
        completion_tokens=raw.get("completion_tokens"),
        total_tokens=raw.get("total_tokens"),
        reasoning_tokens=details.get("reasoning_tokens"),
    )
