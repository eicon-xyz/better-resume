"""Scene mapping for the Xingyun adapter (M5-T4): explicit in, strict out.

The cloud workflow is a black box: we control what we send and what we accept, nothing else.
So this module has exactly two jobs and no fallbacks:

* build the request payload for a scene (one documented shape per scene);
* validate the answer against the caller's Pydantic schema — **no alias guessing** (the old
  project hard-coded \`sugest\`/\`total_score\` style fallbacks; we refuse).
"""

from __future__ import annotations

import json
from typing import Any

import structlog
from pydantic import ValidationError

from .errors import LlmSchemaError
from .firewall import harden_system_prompt, inspect_prompt
from .models import ChatRequest
from .scenes import LlmScene

logger = structlog.get_logger("better_resume.llm_gateway.xingyun")


def validate_structured(schema: type[Any], content: str) -> Any:
    """Parse JSON and validate it against the schema; anything else is a schema error."""
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise LlmSchemaError(f"response is not valid JSON: {exc}") from exc
    try:
        return schema.model_validate(payload)
    except ValidationError as exc:
        raise LlmSchemaError(f"response does not match {schema.__name__}: {exc}") from exc


def to_xingyun_payload(
    scene: LlmScene,
    request: ChatRequest,
    *,
    flow_id: str,
    uid: str,
    stream: bool = True,
) -> dict[str, Any]:
    """The one mapping from our ChatRequest to the workflow payload (§4.1.8 shape)."""
    messages = list(request.messages)
    last_user = next((m.content for m in reversed(messages) if m.role == "user"), "")
    history = [
        {"role": message.role, "content": _harden(message.role, message.content)}
        for message in messages[:-1]
    ]

    parameters: dict[str, Any] = {
        "scene": scene.value,
        "user_input": last_user,
        "uid": uid,
    }
    if request.response_schema is not None:
        # A hint for the workflow prompt; the contract is enforced on our side either way.
        parameters["expect_fields"] = sorted(request.response_schema.model_fields)
    if request.max_tokens is not None:
        parameters["max_tokens"] = request.max_tokens
    if request.temperature is not None:
        parameters["temperature"] = request.temperature

    return {
        "flow_id": flow_id,
        "uid": uid,
        "stream": stream,
        "history": history,
        "parameters": parameters,
    }


def _harden(role: str, content: str) -> str:
    if role != "system":
        return content
    return harden_system_prompt(content)


def inspect_for_injection(messages: list[Any], *, scene: LlmScene, flow_id: str) -> None:
    """Same defence as the OpenAI path: log suspected injections (never silently rewrite)."""
    for message in messages:
        if getattr(message, "role", None) != "user":
            continue
        verdict = inspect_prompt(message.content)
        if verdict.blocked:
            logger.warning(
                "llm_prompt_injection_suspected",
                scene=scene.value,
                flow_id=flow_id,
                patterns=verdict.matched,
            )
