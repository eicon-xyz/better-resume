"""P3: real-machine probe for the DashScope application-call adapter (Xingyun's Alibaba twin).

    uv run python scripts/dashscope_app_probe.py --dry-run   # plan + budget, spends nothing
    uv run python scripts/dashscope_app_probe.py             # 1 vendor call: SSE protocol + timing
    uv run python scripts/dashscope_app_probe.py --schema    # +1 call: structured-output boundary

Refuses to pretend: without `BR_DASHSCOPE_APP_ID` / `BR_DASHSCOPE_API_KEY` (gitignored
`.env`) it exits 2 and spends nothing. Evidence honesty (P19): the usage envelope is printed
**as the vendor sent it** — "this platform returns no usage" is a valid finding, inventing one
is not. Exit codes: 0 ok, 2 missing configuration, 3 the structured contract failed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from typing import Any

from pydantic import BaseModel

from better_resume.llm_gateway import (
    ChatRequest,
    ContentDelta,
    Done,
    LlmScene,
    Message,
    VendorMeta,
    validate_structured,
)
from better_resume.llm_gateway.adapters.dashscope_app import DashScopeAppAdapter
from better_resume.llm_gateway.errors import LlmError
from better_resume.settings import get_settings


class ProbeScore(BaseModel):
    score: float
    feedback: str


PLAIN_PROMPT = "用一句话解释什么是幂等键。"
SCHEMA_PROMPT = (
    "题目：介绍一次性能优化。答案：把 P99 从 800ms 降到 120ms。"
    '请只输出 JSON，形如 {"score": 78, "feedback": "缺少量化"}'
)


def mask(value: str) -> str:
    return f"{value[:8]}…" if len(value) > 8 else "…"


async def probe(
    *, app_id: str, api_key: str, base_url: str, prompt: str, schema: type[BaseModel] | None
) -> int:
    adapter = DashScopeAppAdapter(
        scene=LlmScene.CHAT, app_id=app_id, api_key=api_key, base_url=base_url
    )
    request = ChatRequest(messages=[Message(role="user", content=prompt)], response_schema=schema)
    started = time.perf_counter()
    first_delta_ms: float | None = None
    chunks: list[str] = []
    usage: Any = None
    finish: str | None = None
    try:
        async for event in adapter.stream(request):
            if isinstance(event, ContentDelta):
                if first_delta_ms is None:
                    first_delta_ms = (time.perf_counter() - started) * 1000
                chunks.append(event.text)
            elif isinstance(event, VendorMeta):
                usage = event.extra.get("usage")
            elif isinstance(event, Done):
                finish = event.finish_reason
    except LlmError as exc:
        print(
            json.dumps(
                {"structured": schema is not None, "error": str(exc), "kind": exc.kind.value},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 3
    finally:
        await adapter.aclose()

    text = "".join(chunks)
    report: dict[str, Any] = {
        "app_id": mask(app_id),
        "base_url": base_url,
        "adapter": "dashscope_app",
        "structured": schema is not None,
        "deltas": len(chunks),
        "chars": len(text),
        "first_delta_ms": round(first_delta_ms, 1) if first_delta_ms is not None else None,
        "total_ms": round((time.perf_counter() - started) * 1000, 1),
        "finish_reason": finish,
        "usage_raw": usage,
        "text_head": text[:400],
    }
    if schema is not None:
        try:
            parsed = validate_structured(schema, text)
            report["schema_ok"] = True
            report["parsed"] = parsed.model_dump()
        except LlmError as exc:
            report["schema_ok"] = False
            report["schema_error"] = str(exc)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if schema is not None and not report.get("schema_ok"):
        print(
            "STRUCTURED CONTRACT FAILED -- the boundary finding is in schema_error",
            file=sys.stderr,
        )
        return 3
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--schema",
        action="store_true",
        help="spend one more call on the structured-output boundary",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="print the plan and the budget, spend nothing"
    )
    args = parser.parse_args()

    settings = get_settings()
    app_id = settings.dashscope_app_id
    api_key = settings.dashscope_api_key
    missing = [
        name
        for name, value in (("BR_DASHSCOPE_APP_ID", app_id), ("BR_DASHSCOPE_API_KEY", api_key))
        if not value
    ]
    if missing:
        print(
            f"missing {' and '.join(missing)} (gitignored .env); refusing to pretend",
            file=sys.stderr,
        )
        return 2

    calls = 2 if args.schema else 1
    if args.dry_run:
        print(
            f"DRY RUN -- {calls} vendor call(s) to {settings.dashscope_app_base_url} "
            f"(app {mask(app_id)}); nothing spent"
        )
        return 0

    first = asyncio.run(
        probe(
            app_id=app_id,
            api_key=api_key,
            base_url=settings.dashscope_app_base_url,
            prompt=PLAIN_PROMPT,
            schema=None,
        )
    )
    if first != 0 or not args.schema:
        return first
    return asyncio.run(
        probe(
            app_id=app_id,
            api_key=api_key,
            base_url=settings.dashscope_app_base_url,
            prompt=SCHEMA_PROMPT,
            schema=ProbeScore,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
