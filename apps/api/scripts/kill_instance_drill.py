"""M6-T8: kill the api instance serving an interview and finish it on the survivor.

Run it through scripts/kill_instance_drill.sh (it brings the stack up first):

    bash scripts/kill_instance_drill.sh

The interview runs against the deterministic fake vendor (compose profile "smoke"), so the
numbers are reproducible and no vendor is called. Every claim this drill makes is printed:
which instance answered, kill -> recovery time, the state diff around the kill, and the
Redis key counts for the distributed pieces (locks, hot state, single-flight, job stream).
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
REDIS_PATTERNS = {
    "locks": "br:lock:*",
    "hot_state": "br:hot:*",
    "singleflight": "br:flight:*",
    "jobs": "br:jobs*",
}


def instance_of(response: httpx.Response) -> str:
    return response.headers.get("x-instance-id", "")


DOCKER = shutil.which("docker") or "docker"


def docker(*args: str) -> str:
    # Fixed argv, no shell: the drill only ever runs docker/redis-cli commands.
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
    """Counts per distributed component. Zero is legitimate: locks are released after the
    answer, hot snapshots are invalidated by writes, flight results expire with their replay
    TTL. The drill prints the raw key sample it counted from next to these numbers."""
    counts: dict[str, int] = {}
    for label, pattern in REDIS_PATTERNS.items():
        counts[label] = len(redis_keys(pattern, limit=1000))
    return counts


def snapshot(view: dict[str, Any]) -> dict[str, Any]:
    """What the client can observe about progress. The hot-layer marker is excluded: the hot
    layer may serve the view before the kill and derive it after (that is the point of M6-T3),
    the *state* must be identical."""
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
) -> tuple[str, float]:
    started = time.monotonic()
    while time.monotonic() - started < timeout_seconds:
        try:
            response = await client.get("/healthz", timeout=5.0)
        except httpx.HTTPError:
            await asyncio.sleep(0.2)
            continue
        instance = instance_of(response)
        if response.status_code == 200 and instance and instance != killed:
            return instance, (time.monotonic() - started) * 1000
        await asyncio.sleep(0.2)
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

        # --- answer one question before the kill, remember the request for the replay check
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

        # --- kill exactly the instance that has been serving this session
        kill_started = time.monotonic()
        docker("kill", serving)
        print(f"killed instance {serving}")
        survivor, recovery_ms = await wait_for_another_instance(
            client, killed=serving, timeout_seconds=args.recovery_timeout
        )
        total_ms = (time.monotonic() - kill_started) * 1000
        print(
            f"nginx now routes to {survivor} (first healthy response after {recovery_ms:.0f} ms, "
            f"kill -> recovery {total_ms:.0f} ms)"
        )
        if survivor == serving:
            failures.append("the killed instance answered again")

        # --- the session must still be there, and the replayed request must not re-evaluate
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
        # Counted right after a restore: the hot snapshot for this session exists now.
        print(f"  redis keys mid-flow: {json.dumps(redis_key_counts(), ensure_ascii=False)}")
        if after != before:
            failures.append(f"state changed across the kill: {before} -> {after}")

        # --- finish the interview on whichever instance nginx picks
        submitted = 0
        while submitted < args.max_answers:
            payload = (
                await client.post(
                    f"/api/v1/interview/sessions/{session_id}/answers",
                    json={
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

        # --- the queued report summary must be produced by the worker, not by the api
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
