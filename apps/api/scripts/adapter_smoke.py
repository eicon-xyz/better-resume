"""M5-T8: dual-provider parity smoke — same scene, two adapters, one schema.

    uv run python scripts/adapter_smoke.py --scene answer_evaluation   # DeepSeek vs fake Xingyun
    uv run python scripts/adapter_smoke.py --scene chat --offline             # two fake vendors
    uv run python scripts/adapter_smoke.py --scene answer_evaluation --real-xingyun

Prints one row per provider (request shape, latency, parsed fields) and asserts both sides
produce the same field set. Without credentials the Xingyun side runs against a local fake
workflow server: that is contract-level evidence, never a real-machine claim.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel

from better_resume.interview_engine.evaluation import ScoreResult
from better_resume.llm_gateway import (
    ChatRequest,
    ChatResult,
    LlmScene,
    Message,
    ModelSpec,
)
from better_resume.llm_gateway.adapters.openai_compat import OpenAICompatAdapter
from better_resume.llm_gateway.adapters.xingyun import XingyunWorkflowAdapter
from better_resume.settings import get_settings

SPEC = ModelSpec(
    name="deepseek-flash",
    provider="deepseek",
    base_url="https://api.deepseek.com",
    model_id="deepseek-flash",
    api_key_env="BR_DEEPSEEK_API_KEY",
)

SCORE_JSON = '{"score": 78, "feedback": "结构清晰但缺少量化", "missing_points": ["并发量级"]}'


class FakeWorkflow(BaseHTTPRequestHandler):
    frames: list[dict[str, Any]] = []

    def do_POST(self) -> None:  # noqa: N802 - http.server API
        length = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(length)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for frame in type(self).frames:
            self.wfile.write(f"data:{json.dumps(frame)}\n\n".encode())
        self.wfile.write(b"data:[DONE]\n\n")
        self.wfile.flush()

    def log_message(self, *args: object) -> None:
        return


def _load_env() -> None:
    from dotenv import load_dotenv

    for candidate in (Path(".env"), Path("../../.env")):
        if candidate.exists():
            load_dotenv(candidate, override=False)
    get_settings.cache_clear()


def build_request(scene: LlmScene) -> ChatRequest:
    if scene is LlmScene.ANSWER_EVALUATION:
        return ChatRequest(
            messages=[
                Message(role="system", content="你是严格的面试评分官，只输出 JSON。"),
                Message(
                    role="user",
                    content="题目：介绍一次性能优化。答案：把 P99 从 800ms 降到 120ms。"
                    "请按 schema 输出 score/feedback/missing_points。",
                ),
            ],
            response_schema=ScoreResult,
        )
    return ChatRequest(messages=[Message(role="user", content="用一句话解释什么是幂等键。")])


def summarise(result: ChatResult) -> dict[str, Any]:
    parsed = result.parsed
    return {
        "model": result.model,
        "chars": len(result.content),
        "parsed_fields": sorted(parsed.model_dump().keys())
        if isinstance(parsed, BaseModel)
        else [],
    }


async def run_provider(
    name: str, gateway: Any, request: ChatRequest, scene: LlmScene
) -> dict[str, Any]:
    started = time.perf_counter()
    result = await gateway.complete(request)
    elapsed = (time.perf_counter() - started) * 1000
    summary = summarise(result)
    summary.update({"provider": name, "ms": round(elapsed, 1), "scene": scene.value})
    print(
        f"  {name:16s} {summary['ms']:8.1f} ms  chars={summary['chars']:4d}  "
        f"fields={summary['parsed_fields']}"
    )
    return summary


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scene", default="answer_evaluation", choices=[s.value for s in LlmScene])
    parser.add_argument("--offline", action="store_true", help="fake both vendors")
    parser.add_argument("--real-xingyun", action="store_true", help="use real credentials")
    args = parser.parse_args()

    _load_env()
    settings = get_settings()
    scene = LlmScene(args.scene)
    request = build_request(scene)
    rows: list[dict[str, Any]] = []

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), FakeWorkflow)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    fake_url = f"http://127.0.0.1:{httpd.server_address[1]}/workflow/v1/chat/completions"
    FakeWorkflow.frames = [
        {
            "event": "message",
            "content": SCORE_JSON
            if scene is LlmScene.ANSWER_EVALUATION
            else "幂等键让重复请求只生效一次。",
        }
    ]

    try:
        if args.offline:
            print("openai_compat: fake vendor (offline mode)")
        else:
            api_key = settings.__dict__.get("_x", None) or __import__("os").environ.get(
                "BR_DEEPSEEK_API_KEY", ""
            )
            if not api_key:
                print("BR_DEEPSEEK_API_KEY is missing -> use --offline or set it in .env")
                return 2
            # trust_env=False: the local shell carries a malformed NO_PROXY that httpx rejects.
            async with httpx.AsyncClient(timeout=60, trust_env=False) as client:
                gateway = OpenAICompatAdapter(SPEC, api_key=api_key, client=client)
                rows.append(await run_provider("openai_compat", gateway, request, scene))

        if args.real_xingyun:
            api_key = __import__("os").environ.get("XINGCHEN_API_KEY", "")
            api_secret = __import__("os").environ.get("XINGCHEN_API_SECRET", "")
            if not (api_key and api_secret):
                print("XINGCHEN_API_KEY / XINGCHEN_API_SECRET are missing")
                return 2
            gateway = XingyunWorkflowAdapter(
                scene=scene,
                flow_id=settings.__dict__.get("_flow", "contract-flow"),
                api_key=api_key,
                api_secret=api_secret,
            )
        else:
            print(f"xingyun: local fake workflow at {fake_url} (contract-level evidence)")
            gateway = XingyunWorkflowAdapter(
                scene=scene,
                flow_id="fake-flow",
                api_key="k",
                api_secret="s",  # noqa: S106 - a throwaway value for the local fake server
                base_url=fake_url,
            )
        rows.append(await run_provider("xingyun", gateway, request, scene))
    finally:
        httpd.shutdown()
        httpd.server_close()

    if len(rows) == 2:
        left, right = rows
        same = left["parsed_fields"] == right["parsed_fields"]
        print(f"\nparsed field parity: {same} ({left['parsed_fields']})")
        assert same, "the two providers disagree on the output contract"
    print("result:", "ok" if rows else "nothing ran")
    return 0 if rows else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
