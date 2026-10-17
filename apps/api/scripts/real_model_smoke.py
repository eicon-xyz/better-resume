"""V1：对真实供应商（而非假上游）证明四条 AI 链路。

一切都经 nginx（公开入口），脚本打印 *客户端* 能看到的内容：聊天流里供应商自己的模型名与
token usage、每个面试阶段的结构化字段，以及每一步的计时。

    uv run python -m scripts.real_model_smoke --base-url http://127.0.0.1:8080
    uv run python -m scripts.real_model_smoke --failure-probe

失败探针把一个场景绑定到凭据变量不存在的模型行，期望得到文档化的、点名该变量的 503；之后它
会恢复绑定。
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

from scripts.interview_smoke import ANSWERS, build_resume_pdf

SCENES = ("chat", "question_extraction", "answer_evaluation", "follow_up", "report_summary")
BROKEN_MODEL = "real-smoke-broken"
BROKEN_KEY_ENV = "BR_REAL_SMOKE_MISSING_KEY"
REPO_ROOT = Path(__file__).resolve().parents[3]
BROKEN_MODEL_SQL = """
INSERT INTO ai_models (name, provider, base_url, model_id, api_key_env, max_tokens,
                       temperature, is_enabled, priority, extra)
VALUES ('real-smoke-broken', 'openai_compat', 'https://api.deepseek.com', 'deepseek-flash',
        'BR_REAL_SMOKE_MISSING_KEY', 64, 0.0, true, 999, '{}'::jsonb)
ON CONFLICT (name) DO UPDATE SET api_key_env = EXCLUDED.api_key_env, is_enabled = true;
"""


def ensure_broken_model() -> bool:
    """种下探针用来绑定场景的无凭据模型行（需要 docker）。"""
    docker = shutil.which("docker")
    if docker is None:
        return False
    result = subprocess.run(  # noqa: S603 - 固定 argv，不走 shell
        [
            docker,
            "compose",
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            "better_resume",
            "-d",
            "better_resume",
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            BROKEN_MODEL_SQL,
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
        cwd=REPO_ROOT,
    )
    return result.returncode == 0


def parse_meta(line: str) -> dict[str, Any] | None:
    """`event: meta` + `data: {...}` 是 api 暴露供应商模型与 usage 的方式。"""
    if not line.startswith("data:"):
        return None
    try:
        payload = json.loads(line[len("data:") :].strip())
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or "model" not in payload:
        return None
    return payload


def summarise_steps(steps: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "steps": len(steps),
        "failed": [step["name"] for step in steps if not step.get("ok")],
        "total_ms": round(sum(float(step.get("ms", 0.0)) for step in steps), 1),
        "models": sorted({str(step["model"]) for step in steps if step.get("model")}),
        "total_tokens": sum(
            int((step.get("usage") or {}).get("total_tokens") or 0) for step in steps
        ),
    }


async def run(
    args: argparse.Namespace, *, transport: httpx.AsyncBaseTransport | None = None
) -> int:
    steps: list[dict[str, Any]] = []
    async with httpx.AsyncClient(
        base_url=args.base_url, trust_env=False, timeout=180.0, transport=transport
    ) as client:
        started = time.monotonic()
        login = await client.post(
            "/api/v1/auth/session", json={"user_id": f"v1-{uuid.uuid4().hex[:8]}"}
        )
        login.raise_for_status()
        steps.append({"name": "login", "ok": True, "ms": (time.monotonic() - started) * 1000})

        # --- 第 1 步：聊天流。meta 帧携带供应商的模型 + token usage。
        started = time.monotonic()
        session_id = (await client.post("/api/v1/chat/sessions", json={})).json()["id"]
        content, meta = await _stream_chat(client, session_id, args.prompt)
        steps.append(
            {
                "name": "chat-stream",
                "ok": bool(content) and bool(meta),
                "ms": (time.monotonic() - started) * 1000,
                "model": (meta or {}).get("model"),
                "usage": (meta or {}).get("usage"),
                "chars": len(content),
            }
        )
        print(f"chat: model={(meta or {}).get('model')} usage={(meta or {}).get('usage')}")
        print(f"chat: {content[:120]!r}")

        # --- 第 2-5 步：面试链路，包括 worker 排队的摘要。
        interview_id = (await client.post("/api/v1/interview/sessions", json={})).json()["id"]
        started = time.monotonic()
        generated = await client.post(
            f"/api/v1/interview/sessions/{interview_id}/questions",
            files={"file": ("cv.pdf", build_resume_pdf(), "application/pdf")},
            data={"count": "3"},
        )
        generated.raise_for_status()
        batch = generated.json()
        questions = batch["questions"]
        ok = len(questions) == 3 and all(q["text"] and q["focus_points"] for q in questions)
        steps.append(
            {
                "name": "question-extraction",
                "ok": ok,
                "ms": (time.monotonic() - started) * 1000,
                "questions": len(questions),
                "resume_score": batch["session"]["resume_score"],
            }
        )
        print(f"questions: {len(questions)} resume_score={batch['session']['resume_score']}")

        answered = 0
        while answered < 4:
            view = (await client.get(f"/api/v1/interview/sessions/{interview_id}/restore")).json()
            question_no = view["flow"]["current_question_no"]
            if question_no is None:
                break
            started = time.monotonic()
            submitted = await client.post(
                f"/api/v1/interview/sessions/{interview_id}/answers",
                json={
                    "question_no": question_no,
                    "answer": ANSWERS[min(answered, len(ANSWERS) - 1)],
                    "request_id": f"v1-{answered}",
                },
            )
            submitted.raise_for_status()
            payload = submitted.json()
            steps.append(
                {
                    "name": f"answer-{question_no}",
                    "ok": payload["answer"]["score"] is not None,
                    "ms": (time.monotonic() - started) * 1000,
                    "score": payload["answer"]["score"],
                    "next_action": payload["next_action"],
                    "follow_up_reason": payload["answer"]["follow_up_reason"],
                }
            )
            print(
                f"answered {question_no}: score={payload['answer']['score']} "
                f"next={payload['next_action']} reason={payload['answer']['follow_up_reason']}"
            )
            answered += 1
            if payload["next_action"] == "finished":
                break

        started = time.monotonic()
        finished = await client.post(f"/api/v1/interview/sessions/{interview_id}/finish")
        finished.raise_for_status()
        report = finished.json()
        steps.append(
            {
                "name": "finish",
                "ok": report["overall_score"] is not None,
                "ms": (time.monotonic() - started) * 1000,
                "overall": report["overall_score"],
                "turns": len(report["turns"]),
                "summary_pending": report.get("summary_pending"),
            }
        )
        print(
            f"finish: overall={report['overall_score']} turns={len(report['turns'])} "
            f"summary_pending={report.get('summary_pending')}"
        )

        started = time.monotonic()
        summary = None
        deadline = time.monotonic() + args.summary_timeout
        while time.monotonic() < deadline:
            await asyncio.sleep(1)
            current = (await client.get(f"/api/v1/interview/sessions/{interview_id}/report")).json()
            if current.get("summary"):
                summary = current["summary"]
                break
        steps.append(
            {
                "name": "report-summary(worker)",
                "ok": bool(summary),
                "ms": (time.monotonic() - started) * 1000,
                "chars": len(summary or ""),
            }
        )
        print(f"worker summary after {(time.monotonic() - started):.1f}s: {summary!r}")

        if args.failure_probe:
            await _failure_probe(client, args, steps)

    result = summarise_steps(steps)
    print("\n== real-model summary ==")
    print(json.dumps({"summary": result, "steps": steps}, ensure_ascii=False, indent=2))
    if args.json:
        payload = {"summary": result, "steps": steps}
        await asyncio.to_thread(
            Path(args.json).write_text,
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print("json ->", args.json)
    return 0 if not result["failed"] else 1


async def _stream_chat(
    client: httpx.AsyncClient, session_id: str, prompt: str
) -> tuple[str, dict[str, Any] | None]:
    content: list[str] = []
    meta: dict[str, Any] | None = None
    async with client.stream(
        "POST", f"/api/v1/chat/sessions/{session_id}/stream", json={"content": prompt}
    ) as response:
        response.raise_for_status()
        async for line in response.aiter_lines():
            stripped = line.strip()
            if stripped.startswith("data:"):
                payload = parse_meta(stripped)
                if payload is not None:
                    meta = payload
                    continue
                try:
                    body = json.loads(stripped[len("data:") :].strip())
                except json.JSONDecodeError:
                    continue
                if isinstance(body, dict) and body.get("text"):
                    content.append(str(body["text"]))
    return "".join(content), meta


async def _failure_probe(
    client: httpx.AsyncClient, args: argparse.Namespace, steps: list[dict[str, Any]]
) -> None:
    """绑定到无凭据模型的场景必须以文档化的 503 失败。"""
    if not ensure_broken_model():
        steps.append(
            {
                "name": "failure-probe(missing credential)",
                "ok": True,
                "skipped": "docker is not available to seed the credential-less model row",
            }
        )
        print("failure probe skipped: docker not available")
        return

    original = (await client.get("/api/v1/scenes")).json()
    chat_binding = next(row for row in original if row["scene"] == "chat")
    try:
        switched = await client.put(
            "/api/v1/scenes/chat",
            json={"adapter": "openai_compat", "target_ref": BROKEN_MODEL},
        )
        switched.raise_for_status()
        started = time.monotonic()
        session_id = (await client.post("/api/v1/chat/sessions", json={})).json()["id"]
        # 模型注册表缓存 30s，所以首次尝试可能仍看到旧列表。
        response = None
        detail = ""
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            response = await client.post(
                f"/api/v1/chat/sessions/{session_id}/stream", json={"content": "你好"}
            )
            with contextlib.suppress(Exception):
                detail = response.json().get("detail", "")
            if response.status_code == 503 and BROKEN_KEY_ENV in detail:
                break
            await asyncio.sleep(5)
        assert response is not None
        steps.append(
            {
                "name": "failure-probe(missing credential)",
                "ok": response.status_code == 503 and BROKEN_KEY_ENV in detail,
                "ms": (time.monotonic() - started) * 1000,
                "status": response.status_code,
                "detail": detail,
            }
        )
        print(f"failure probe: {response.status_code} {detail}")
    finally:
        await client.put(
            "/api/v1/scenes/chat",
            json={"adapter": chat_binding["adapter"], "target_ref": chat_binding["target_ref"]},
        )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="V1 real-vendor smoke (through nginx)")
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--prompt", default="请用一句话说明你为什么适合这个岗位。")
    parser.add_argument("--summary-timeout", type=float, default=120.0)
    parser.add_argument("--failure-probe", action="store_true")
    parser.add_argument("--json")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(run(parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main())
