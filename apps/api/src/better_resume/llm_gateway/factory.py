"""Build the gateway for a registry row; swapped out in tests via app.state."""

from __future__ import annotations

from .adapters import OpenAICompatAdapter
from .models import ModelSpec
from .protocols import LlmGateway


def build_llm_gateway(spec: ModelSpec, api_key: str) -> LlmGateway:
    return OpenAICompatAdapter(spec, api_key=api_key)
