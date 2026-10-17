"""kill 掉正在服务一场面试的 api 实例，并在幸存实例上完成它。

通过 scripts/kill_instance_drill.sh 运行（它会先把栈拉起来）：

    bash scripts/kill_instance_drill.sh

面试打到确定性的假供应商（compose profile "smoke"），所以数字可复现，且不会调用任何供应商。
这次演练作出的每条声明都会打印：哪个实例应答、kill -> 恢复耗时、kill 前后的状态 diff，以及
分布式部件的 Redis key 计数（锁、热状态、单飞、作业流）。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import subprocess
import sys
import time
from typing import Any

import httpx

from scripts.interview_smoke import ANSWERS, build_resume_pdf

SCENES = ("chat", "question_extraction", "answer_evaluation", "follow_up", "report_summary")
#: kill 后的首个请求可能被已死的上游卡住，直到 nginx 判它失败。
#: 用短客户端超时轮询，让上报的数字衡量 nginx，而不是探针。
PROBE_TIMEOUT_SECONDS = 1.0

REDIS_PATTERNS = {
    "locks": "br:lock:*",
    "hot_state": "br:hot:*",
    "singleflight": "br:flight:*",
    "jobs": "br:jobs*",
}


def instance_of(response: httpx.Response) -> str:
    return response.headers.get("x-instance-id", "")


def retry_after_seconds(response: httpx.Response, *, default: float = 1.0) -> float:
    """限流器的 Retry-After 是它契约的一部分；照它办，不要猜。"""
    raw = response.headers.get("retry-after")
    if raw is None:
        return default
    try:
        return max(0.0, float(raw))
    except ValueError:
        return default


async def post_answer(
    client: httpx.AsyncClient, url: str, body: dict[str, Any], *, attempts: int = 5
) -> httpx.Response:
    """答题桶是 2 rps、2 倍突发（校准：docs/perf/capacity.md §2.7），而这次演练以假供应商应答的
    最快速度发答案，所以 429 是预期而不是失败。按 Retry-After 重试同一个 request_id（端点幂等）。
    其他错误连同响应体一起抛出——一个裸的 `KeyError: 'next_action'` 曾把问题藏了一整轮，读起来
    像服务端 bug。
    """
    response = await client.post(url, json=body)
    for _ in range(attempts - 1):
        if response.status_code != 429:
            break
        delay = retry_after_seconds(response)
        print(f"  answer rate limited (429); retrying in {delay:.2f}s")
        await asyncio.sleep(delay)
        response = await client.post(url, json=body)
    if response.status_code >= 400:
        raise RuntimeError(f"HTTP {response.status_code} from {url}: {response.text[:200]}")
    return response


DOCKER = shutil.which("docker") or "docker"


def docker(*args: str) -> str:
    # 固定 argv，不走 shell：演练只跑 docker/redis-cli 命令。
    result = subprocess.run(  # noqa: S603
        [DOCKER, *args], capture_output=True, text=True, check=False, timeout=120
    )
    if result.returncode != 0:
        raise RuntimeError(f"docker {' '.join(args)} failed: {result.stderr.strip()[:200]}")
    return result.stdout.strip()


def redis_keys(pattern: str = "br:*", *, limit: int = 40) -> list[str]:
    out = docker("compose", "exec", "-T", "redis", "redis-cli", "--scan", "--pattern", pattern)
    return [line.strip() for line in out.splitlines() if line.strip()][:limit]


def redis_key_counts() -> dict[str, int]:
    """每个分布式部件的计数。零是合法的：锁在答题后释放，热快照被写操作失效，单飞结果随回放 TTL
    过期。演练会在这些数字旁边打印它所依据的原始 key 样本。"""
    counts: dict[str, int] = {}
    for label, pattern in REDIS_PATTERNS.items():
        counts[label] = len(redis_keys(pattern, limit=1000))
    return counts


def snapshot(view: dict[str, Any]) -> dict[str, Any]:
    """客户端能观察到的进度。排除热层标记：热层可能在 kill 前提供该视图、在 kill 后推导出来
    （这正是热状态的意义），而 *状态* 必须一致。"""
    flow = view.get("flow") or {}
    return {
        "status": flow.get("status"),
        "current_question_no": flow.get("current_question_no"),
        "answered": view.get("answered"),
        "total_questions": view.get("total_questions"),
        "last_score": (view.get("last_answer") or {}).get("score"),
        "last_question_no": (view.get("last_answer") or {}).get("question_no"),
    }


def report_numbers(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "overall": report.get("overall_score"),
        "dimensions": {item["key"]: item["score"] for item in report.get("dimensions", [])},
        "turns": [
            (turn.get("question_no"), turn.get("kind"), turn.get("score"))
            for turn in report.get("turns", [])
        ],
        "suggestions": report.get("suggestions"),
    }


async def bind_every_scene_to_the_fake(client: httpx.AsyncClient, model: str) -> None:
    for scene in SCENES:
        response = await client.put(
            f"/api/v1/scenes/{scene}", json={"adapter": "openai_compat", "target_ref": model}
        )
        response.raise_for_status()
    print(f"scenes -> {model}: {', '.join(SCENES)}")


async def wait_for_another_instance(
    client: httpx.AsyncClient, *, killed: str, timeout_seconds: float
) -> tuple[str, float, int]:
    started = time.monotonic()
    attempts = 0
    while time.monotonic() - started < timeout_seconds:
        attempts += 1
        try:
            response = await client.get("/healthz", timeout=PROBE_TIMEOUT_SECONDS)
        except httpx.HTTPError:
            await asyncio.sleep(0.1)
            continue
        instance = instance_of(response)
        if response.status_code == 200 and instance and instance != killed:
            return instance, (time.monotonic() - started) * 1000, attempts
        await asyncio.sleep(0.1)
    raise TimeoutError(f"no surviving instance answered within {timeout_seconds}s")


async def run(args: argparse.Namespace) -> int:
    failures: list[str] = []
    async with httpx.AsyncClient(base_url=args.base, timeout=120.0, trust_env=False) as client:
        login = await client.post(
            "/api/v1/auth/session", json={"user_id": f"drill-{int(time.time())}"}
        )
        login.raise_for_status()
        print(f"login: {login.status_code} instance={instance_of(login)}")

        await bind_every_scene_to_the_fake(client, args.model)

        session_id = (await client.post("/api/v1/interview/sessions", json={})).json()["id"]
        generated = await client.post(
            f"/api/v1/interview/sessions/{session_id}/questions",
            files={"file": ("cv.pdf", build_resume_pdf(), "application/pdf")},
            data={"count": "3"},
        )
        generated.raise_for_status()
        serving = instance_of(generated)
        print(f"questions: {len(generated.json()['questions'])} generated by instance={serving}")

        # --- kill 前先答一题，记住请求以便回放检查
        view = (await client.get(f"/api/v1/interview/sessions/{session_id}/restore")).json()
        question_no = view["flow"]["current_question_no"]
        replay_body = {
            "question_no": question_no,
            "answer": ANSWERS[0],
            "request_id": "drill-replay-1",
        }
        answered = await client.post(
            f"/api/v1/interview/sessions/{session_id}/answers", json=replay_body
        )
        answered.raise_for_status()
        serving = instance_of(answered)
        before = snapshot(
            (await client.get(f"/api/v1/interview/sessions/{session_id}/restore")).json()
        )
        print(
            f"answered {question_no}: score={answered.json()['answer']['score']} "
            f"instance={serving}\n  state before kill: {json.dumps(before, ensure_ascii=False)}"
        )

        # --- 精确 kill 掉一直在服务这个会话的实例
        kill_started = time.monotonic()
        docker("kill", serving)
        print(f"killed instance {serving}")
        survivor, recovery_ms, attempts = await wait_for_another_instance(
            client, killed=serving, timeout_seconds=args.recovery_timeout
        )
        total_ms = (time.monotonic() - kill_started) * 1000
        print(
            f"nginx now routes to {survivor} (first healthy response after {recovery_ms:.0f} ms "
            f"in {attempts} attempts of {PROBE_TIMEOUT_SECONDS:.0f}s, "
            f"kill -> recovery {total_ms:.0f} ms)"
        )
        if survivor == serving:
            failures.append("the killed instance answered again")

        # --- 会话必须仍在，且回放的请求不得重评
        replay = await client.post(
            f"/api/v1/interview/sessions/{session_id}/answers", json=replay_body
        )
        replay.raise_for_status()
        replay_payload = replay.json()
        replay_instance = instance_of(replay)
        print(
            f"replayed request on {replay_instance}: replayed={replay_payload['replayed']} "
            f"score={replay_payload['answer']['score']}"
        )
        if not replay_payload["replayed"]:
            failures.append("the replayed answer was evaluated a second time")
        if replay_payload["answer"]["score"] != answered.json()["answer"]["score"]:
            failures.append("the replay changed the stored score")

        after = snapshot(
            (await client.get(f"/api/v1/interview/sessions/{session_id}/restore")).json()
        )
        print(f"  state after kill:  {json.dumps(after, ensure_ascii=False)}")
        # 紧跟在一次 restore 之后计数：此时该会话的热快照存在。
        print(f"  redis keys mid-flow: {json.dumps(redis_key_counts(), ensure_ascii=False)}")
        if after != before:
            failures.append(f"state changed across the kill: {before} -> {after}")

        # --- 在 nginx 挑中的任意实例上完成面试
        submitted = 0
        while submitted < args.max_answers:
            payload = (
                await post_answer(
                    client,
                    f"/api/v1/interview/sessions/{session_id}/answers",
                    {
                        "question_no": (
                            await client.get(f"/api/v1/interview/sessions/{session_id}/restore")
                        ).json()["flow"]["current_question_no"],
                        "answer": ANSWERS[min(submitted + 1, len(ANSWERS) - 1)],
                        "request_id": f"drill-{submitted + 2}",
                    },
                )
            ).json()
            submitted += 1
            if payload["next_action"] == "finished" or payload.get("next_question_no") is None:
                break

        finished = await client.post(f"/api/v1/interview/sessions/{session_id}/finish")
        finished.raise_for_status()
        report = finished.json()
        print(
            f"finish: status={report['session']['status']} overall={report['overall_score']} "
            f"turns={len(report['turns'])} summary_pending={report.get('summary_pending')} "
            f"instance={instance_of(finished)}"
        )

        # --- 排队的报告摘要必须由 worker 产出，而不是 api
        summary = report.get("summary")
        deadline = time.monotonic() + args.summary_timeout
        while not summary and time.monotonic() < deadline:
            await asyncio.sleep(0.5)
            summary = (await client.get(f"/api/v1/interview/sessions/{session_id}/report")).json()[
                "summary"
            ]
        print(f"report summary from the worker: {summary!r}")
        if not summary:
            failures.append("the worker did not fill the report summary in time")

        numbers = report_numbers(
            (await client.get(f"/api/v1/interview/sessions/{session_id}/report")).json()
        )
        printed = report_numbers(report)
        if numbers["turns"] != printed["turns"] or numbers["overall"] != printed["overall"]:
            failures.append("the frozen report changed after the kill")
        if before["last_score"] is None or before["last_score"] not in [
            score for _no, _kind, score in numbers["turns"]
        ]:
            failures.append("the pre-kill score is missing from the frozen report")
        print(f"frozen report: {json.dumps(numbers, ensure_ascii=False)}")

    counts = redis_key_counts()
    sample = redis_keys()
    print(f"redis keys at the end: {json.dumps(counts, ensure_ascii=False)}")
    print(f"redis key sample: {json.dumps(sample, ensure_ascii=False)}")

    print("\n== drill summary ==")
    print(f"instances: served={serving} survivor={survivor} kill->recovery={total_ms:.0f} ms")
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print("PASS: 会话在实例被 kill 后由另一实例接管，状态、分数与冻结报告全部一致")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="kill-instance drill (through nginx)")
    parser.add_argument("--base", default="http://127.0.0.1:8080")
    parser.add_argument("--model", default="smoke-fake")
    parser.add_argument("--max-answers", type=int, default=8)
    parser.add_argument("--recovery-timeout", type=float, default=30.0)
    parser.add_argument("--summary-timeout", type=float, default=30.0)
    return parser.parse_args(argv)


if __name__ == "__main__":
    sys.exit(asyncio.run(run(parse_args())))
