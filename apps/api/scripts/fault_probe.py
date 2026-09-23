"""V6: soak sampling and fault injection for the distributed pieces.

Everything here talks to the stack through nginx (never straight into a container) and injects
faults with docker, so the evidence is "what a client saw while Redis/worker were broken".

Run it through \`scripts/fault_injection_drill.sh\`, or by hand:

    uv run python -m scripts.fault_probe soak --duration 1200
    uv run python -m scripts.fault_probe fault --scenario redis-pause --seconds 20
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
from scripts.kill_instance_drill import bind_every_scene_to_the_fake

#: A client that waits longer than this is reporting its own patience, not the outage.
PROBE_TIMEOUT_SECONDS = 2.0

DOCKER = shutil.which("docker") or "docker"
#: P1-D: the throwaway replica used by the failover drill.
REPLICA_NAME = "br-redis-replica"
POSTGRES_USER = "better_resume"
POSTGRES_DB = "better_resume"

_COUNTER_KEYS = (
    "ok",
    "rate_limited",
    "client_error",
    "server_error",
    "timeout",
    "transport",
    "unexpected",
)


def docker(*args: str) -> str:
    """Fixed argv, no shell: the probe only ever runs docker/redis-cli/psql commands."""
    result = subprocess.run(  # noqa: S603
        [DOCKER, *args], capture_output=True, text=True, check=False, timeout=180
    )
    if result.returncode != 0:
        raise RuntimeError(f"docker {' '.join(args)} failed: {result.stderr.strip()[:200]}")
    return result.stdout.strip()


def parse_replica_link(info: str) -> str:
    """'up' / 'down' / 'unknown' from a replica's INFO replication output (P1-D)."""
    for line in info.splitlines():
        key, _, value = line.strip().partition(":")
        if key == "master_link_status":
            return value.strip() or "unknown"
    return "unknown"


def service_container(service: str) -> str:
    ids = docker("compose", "ps", "-q", service).split()
    if not ids:
        raise RuntimeError(f"service {service!r} has no running container")
    return ids[0]


def compose_network(container: str) -> str:
    names = docker(
        "inspect", "-f", "{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}", container
    ).split()
    if not names:
        raise RuntimeError(f"container {container} is not attached to any network")
    return names[0]


def container_image(container: str) -> str:
    return docker("inspect", "-f", "{{.Config.Image}}", container)


def try_docker(*args: str) -> None:
    with contextlib.suppress(RuntimeError):
        docker(*args)


def classify_response(*, status: int | None = None, exc: BaseException | None = None) -> str:
    """One name per outcome, so a fault window can be read as counts instead of prose."""
    if exc is not None:
        if isinstance(exc, httpx.TimeoutException):
            return "timeout"
        if isinstance(exc, httpx.HTTPError):
            return "transport"
        return "unexpected"
    if status is None:
        return "unexpected"
    if status == 429:
        return "rate_limited"
    if status >= 500:
        return "server_error"
    if status >= 400:
        return "client_error"
    return "ok"


def summarise_waves(waves: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate per-wave counters plus the first->last growth of the sampled gauges."""
    kinds: dict[str, int] = {}
    for wave in waves:
        for key in _COUNTER_KEYS:
            value = int(wave.get(key, 0))
            if value:
                kinds[key] = kinds.get(key, 0) + value
    total = sum(kinds.values())
    failures = total - kinds.get("ok", 0)
    first = waves[0] if waves else {}
    last = waves[-1] if waves else {}
    return {
        "waves": len(waves),
        "total": total,
        "ok": kinds.get("ok", 0),
        "failures": failures,
        "error_rate": (failures / total) if total else 0.0,
        "kinds": dict(sorted(kinds.items())),
        "redis_keys_growth": int(last.get("redis_keys", 0)) - int(first.get("redis_keys", 0)),
        "redis_sessions_growth": int(last.get("redis_sessions", 0))
        - int(first.get("redis_sessions", 0)),
        "redis_other_keys_growth": (
            int(last.get("redis_keys", 0))
            - int(last.get("redis_sessions", 0))
            - (int(first.get("redis_keys", 0)) - int(first.get("redis_sessions", 0)))
        ),
        "redis_memory_mb_growth": round(
            float(last.get("redis_memory_mb", 0.0)) - float(first.get("redis_memory_mb", 0.0)), 2
        ),
        "pg_connections_growth": int(last.get("pg_connections", 0))
        - int(first.get("pg_connections", 0)),
        "api_memory_mb_growth": round(
            float(last.get("api_memory_mb", 0.0)) - float(first.get("api_memory_mb", 0.0)), 1
        ),
    }


# ---- gauges ---------------------------------------------------------------------


def redis_gauges() -> dict[str, float]:
    """Keys, sessions and memory. Sessions are the probe's own churn (30-day TTL), so the
    interesting number is everything else plus the memory trend."""
    keys = docker("compose", "exec", "-T", "redis", "redis-cli", "DBSIZE")
    sessions = docker(
        "compose", "exec", "-T", "redis", "redis-cli", "--scan", "--pattern", "session:*"
    )
    memory = docker("compose", "exec", "-T", "redis", "redis-cli", "INFO", "memory")
    used = 0.0
    for line in memory.splitlines():
        if line.startswith("used_memory:"):
            used = round(int(line.split(":", 1)[1]) / (1024 * 1024), 2)
    session_count = len([row for row in sessions.splitlines() if row.strip()])
    return {
        "redis_keys": int(keys or 0),
        "redis_sessions": session_count,
        "redis_memory_mb": used,
    }


def pg_connection_count() -> int:
    out = docker(
        "compose",
        "exec",
        "-T",
        "postgres",
        "psql",
        "-U",
        POSTGRES_USER,
        "-d",
        POSTGRES_DB,
        "-tAc",
        "select count(*) from pg_stat_activity where datname = current_database()",
    )
    return int(out or 0)


def api_memory_mb() -> float:
    out = docker("stats", "--no-stream", "--format", "{{.Name}} {{.MemUsage}}")
    total = 0.0
    for line in out.splitlines():
        name, _, usage = line.partition(" ")
        if "better-resume-api" not in name:
            continue
        amount = usage.split("/")[0].strip()
        number = float("".join(ch for ch in amount if ch.isdigit() or ch == ".") or 0)
        total += number / (1024 if amount.endswith("GiB") else 1)
    return round(total, 1)


# ---- probes ---------------------------------------------------------------------


def _session_payload() -> dict[str, str]:
    return {"user_id": f"v6-{uuid.uuid4().hex[:8]}"}


async def probe_once(client: httpx.AsyncClient, *, create_session: bool = True) -> str:
    """Liveness plus a Redis/DB read; only some probes write a new session.

    Creating a session on every probe would dwarf every other Redis number (30-day TTL),
    so the soak logs in once and re-reads "/auth/me" for the rest of the run."""
    try:
        health = await client.get("/healthz", timeout=PROBE_TIMEOUT_SECONDS)
    except httpx.HTTPError as exc:
        return classify_response(exc=exc)
    if health.status_code >= 400:
        return classify_response(status=health.status_code)
    path = "/api/v1/auth/session" if create_session else "/api/v1/auth/me"
    try:
        if create_session:
            response = await client.post(
                path, json=_session_payload(), timeout=PROBE_TIMEOUT_SECONDS
            )
        else:
            response = await client.get(path, timeout=PROBE_TIMEOUT_SECONDS)
    except httpx.HTTPError as exc:
        return classify_response(exc=exc)
    return classify_response(status=response.status_code)


async def run_wave(
    client: httpx.AsyncClient, *, requests: int, concurrency: int, logins: int = 2
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for index in range(requests):
        create = index < logins  # a couple of writes per wave, then reads only
        outcome = await probe_once(client, create_session=create)
        counts[outcome] = counts.get(outcome, 0) + 1
        if (index + 1) % concurrency == 0:
            await asyncio.sleep(0)
    return counts


async def login_with_retry(
    client: httpx.AsyncClient, *, attempts: int = 5, delay: float = 1.0
) -> httpx.Response:
    """P37: a fault experiment leaves brief stale connections behind, and a 503 is the
    documented "dependency is down" answer (P17) — retry the login instead of aborting the
    next experiment on one bad response.

    The soak grew this loop first ("observed after a failover"); worker-crash runs straight
    after the failover experiment and hit the same 503, so the loop lives here now and both
    callers share it.
    """
    response = await client.post("/api/v1/auth/session", json=_session_payload())
    for attempt in range(attempts - 1):
        if response.status_code < 400:
            break
        print(f"== login attempt {attempt + 1} -> {response.status_code}; retrying in {delay:.1f}s")
        await asyncio.sleep(delay)
        response = await client.post("/api/v1/auth/session", json=_session_payload())
    response.raise_for_status()
    return response


def write_json(path: str, payload: dict[str, Any]) -> None:
    """P39: never lose a run to a missing directory.

    An hour-long soak finished, passed, and then died writing its evidence: `verify.sh --layer
    soak` runs with cwd=apps/api, so `--json var/evidence/soak-60m.json` pointed at
    apps/api/var/evidence/ (which does not exist) while the weekly workflow collects
    var/evidence/ from the repo root.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


async def wait_until_the_stack_is_usable(
    client: httpx.AsyncClient, *, model: str, budget_seconds: float, delay: float = 2.0
) -> None:
    """P38: worker-crash runs straight after the failover experiment puts the original
    master back, and the scene/registry caches answer 503 for a while after that (P17
    "dependency unavailable"). The experiment is about reclaiming a crashed consumer's job,
    not about surviving a cold cache — so wait for the stack to be usable, and still fail
    loudly if it never is.
    """
    try:
        async with asyncio.timeout(budget_seconds):
            while True:
                try:
                    await login_with_retry(client, attempts=2, delay=1.0)
                    await bind_every_scene_to_the_fake(client, model)
                    return
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code != 503:
                        raise
                    print(
                        f"== stack not usable yet ({exc.response.status_code}); "
                        f"retrying in {delay:.0f}s"
                    )
                    await asyncio.sleep(delay)
    except TimeoutError as exc:
        raise RuntimeError(f"the stack still answered 503 after {budget_seconds:.0f}s") from exc


async def soak(args: argparse.Namespace) -> int:
    waves: list[dict[str, Any]] = []
    deadline = time.monotonic() + args.duration
    async with httpx.AsyncClient(base_url=args.base, trust_env=False) as client:
        await login_with_retry(client)
        while time.monotonic() < deadline:
            started = time.monotonic()
            wave = await run_wave(client, requests=args.requests, concurrency=args.concurrency)
            wave.update(redis_gauges())
            wave["pg_connections"] = pg_connection_count()
            wave["api_memory_mb"] = api_memory_mb()
            wave["at_seconds"] = round(time.monotonic() - (deadline - args.duration), 1)
            waves.append(wave)
            print(json.dumps(wave, ensure_ascii=False), flush=True)
            sleep_for = args.wave_seconds - (time.monotonic() - started)
            if sleep_for > 0:
                await asyncio.sleep(sleep_for)

    summary = summarise_waves(waves)
    print("\n== soak summary ==")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"duration_s={args.duration} requests_per_wave={args.requests}")
    if args.json:
        payload = {"waves": waves, "summary": summary, "args": vars(args)}
        await asyncio.to_thread(write_json, args.json, payload)
        print("json ->", args.json)
    return 0 if summary["error_rate"] < 0.01 else 1


async def fault(args: argparse.Namespace) -> int:
    counts: dict[str, int] = {}
    redis_ct = ""
    network = ""
    notes: list[str] = []
    async with httpx.AsyncClient(base_url=args.base, trust_env=False) as client:
        if args.scenario == "redis-pause":
            print(f"== pausing redis for {args.seconds}s (docker pause)")
            injected = time.monotonic()
            docker("compose", "pause", "redis")
        elif args.scenario == "redis-restart":
            print("== restarting redis (sessions live there: expect logouts)")
            login = await client.post("/api/v1/auth/session", json=_session_payload())
            cookie = "; ".join(f"{k}={v}" for k, v in login.cookies.items())
            injected = time.monotonic()
            docker("compose", "restart", "redis")
            await asyncio.sleep(2)
            async with httpx.AsyncClient(
                base_url=args.base,
                trust_env=False,
                cookies={"br_session": cookie.split("=", 1)[-1]},
            ) as old:
                me = await old.get("/api/v1/auth/me", timeout=PROBE_TIMEOUT_SECONDS)
            print(f"old cookie after restart: {me.status_code} (401 = session really gone)")
        elif args.scenario == "redis-partition":
            redis_ct = service_container("redis")
            network = compose_network(redis_ct)
            # A session must exist BEFORE the cut, otherwise /auth/me answers 401 for the
            # (correct) reason "no cookie" and hides the question we are actually asking.
            login = await client.post("/api/v1/auth/session", json=_session_payload())
            login.raise_for_status()
            print(f"== cutting the api<->redis path for {args.seconds}s (network disconnect)")
            injected = time.monotonic()
            docker("network", "disconnect", network, redis_ct)
        elif args.scenario == "redis-failover":
            redis_ct = service_container("redis")
            network = compose_network(redis_ct)
            image = container_image(redis_ct)
            login = await client.post("/api/v1/auth/session", json=_session_payload())
            login.raise_for_status()
            print(f"== starting a replica of redis ({image}) and waiting for a full sync")
            try_docker("rm", "-f", REPLICA_NAME)
            docker(
                "run",
                "-d",
                "--name",
                REPLICA_NAME,
                "--network",
                network,
                image,
                "redis-server",
                "--replicaof",
                "redis",
                "6379",
            )
            link, master_keys, replica_keys = "unknown", -1, -1
            sync_deadline = time.monotonic() + 45
            while time.monotonic() < sync_deadline:
                link = parse_replica_link(
                    docker("exec", REPLICA_NAME, "redis-cli", "info", "replication")
                )
                if link == "up":
                    master_keys = int(docker("exec", redis_ct, "redis-cli", "dbsize") or 0)
                    replica_keys = int(docker("exec", REPLICA_NAME, "redis-cli", "dbsize") or 0)
                    if master_keys > 0 and replica_keys >= master_keys:
                        break
                await asyncio.sleep(1)
            print(f"== replica link={link} dbsize master={master_keys} replica={replica_keys}")
            if link != "up" or replica_keys < master_keys:
                print("FAIL: replica never caught up; aborting before touching the master")
                try_docker("rm", "-f", REPLICA_NAME)
                return 2
            injected = time.monotonic()
            docker("compose", "stop", "redis")
            docker("exec", REPLICA_NAME, "redis-cli", "REPLICAOF", "NO", "ONE")
            docker("network", "disconnect", network, REPLICA_NAME)
            docker("network", "connect", "--alias", "redis", network, REPLICA_NAME)
            print("== master stopped; replica promoted and now answers to the name 'redis'")
        else:
            raise SystemExit(f"unknown scenario {args.scenario!r}")

        health_ok = 0
        auth_sampled = False
        try:
            while time.monotonic() - injected < args.seconds:
                outcome = await probe_once(client)
                counts[outcome] = counts.get(outcome, 0) + 1
                if args.scenario == "redis-partition":
                    health = await client.get("/healthz", timeout=PROBE_TIMEOUT_SECONDS)
                    health_ok += 1 if health.status_code == 200 else 0
                    if not auth_sampled:
                        auth_sampled = True
                        try:
                            me = await client.get("/api/v1/auth/me", timeout=PROBE_TIMEOUT_SECONDS)
                            notes.append(f"auth_status_during_partition={me.status_code}")
                            notes.append(f"retry_after={me.headers.get('retry-after')!r}")
                        except httpx.HTTPError as exc:
                            notes.append(f"auth_during_partition={type(exc).__name__}")
                await asyncio.sleep(0.2)
        finally:
            # The drill must never leave the stack cut off, whatever happened above.
            if args.scenario == "redis-partition":
                docker("network", "connect", "--alias", "redis", network, redis_ct)
        if args.scenario == "redis-partition":
            notes.append(f"healthz_ok_during_partition={health_ok}")

        if args.scenario == "redis-pause":
            docker("compose", "unpause", "redis")
            print("== redis unpaused, waiting for the first success")
        if args.scenario == "redis-partition":
            print("== network path restored, waiting for the first success")
        recovered_at: float | None = None
        deadline = time.monotonic() + args.recovery_timeout
        while time.monotonic() < deadline:
            if await probe_once(client) == "ok":
                recovered_at = time.monotonic()
                break
            await asyncio.sleep(0.2)

        if args.scenario == "redis-failover":
            try:
                me = await client.get("/api/v1/auth/me", timeout=PROBE_TIMEOUT_SECONDS)
                notes.append(f"old_session_after_failover={me.status_code}")
            except httpx.HTTPError as exc:
                notes.append(f"old_session_after_failover={type(exc).__name__}")
            notes.append(
                "worker_health="
                + docker("inspect", "-f", "{{.State.Health.Status}}", service_container("worker"))
            )
            print("== restoring the original topology (replica removed, master back)")
            try_docker("rm", "-f", REPLICA_NAME)
            docker("compose", "up", "-d", "--wait", "redis")
            notes.append("topology_restored=true")

    total = sum(counts.values())
    print(f"fault window: {json.dumps(dict(sorted(counts.items())), ensure_ascii=False)}")
    if recovered_at is None:
        print("FAIL: no successful request after recovery")
        return 1
    recovery_ms = ((recovered_at - injected) - args.seconds) * 1000
    print(f"recovery: {recovery_ms:.0f} ms after the fault ended")
    print(f"total={total} ok_during_fault={counts.get('ok', 0)}")
    for note in notes:
        print(f"note: {note}")
    return 0


CLAIM_SNIPPET = """
import asyncio
from better_resume.jobs.queue import JobQueue
from better_resume.settings import get_settings

async def main():
    settings = get_settings()
    queue = JobQueue(settings.redis_url, stream=settings.jobs_stream)
    jobs = await queue.claim(consumer='v6-crash-sim', count=1, block_ms=200)
    print('v6-claimed', [job.task_id for job in jobs])
    await queue.close()

asyncio.run(main())
"""


async def worker_crash(args: argparse.Namespace) -> int:
    """A consumer that dies holding a job must not lose it: the worker reclaims it.

    The job is claimed by a one-off container that exits without acking, which is exactly
    what a crash looks like from Redis' side; the real worker then has to take it over
    through XPENDING+XCLAIM once the entry has been idle for the reclaim threshold.
    """
    async with httpx.AsyncClient(base_url=args.base, trust_env=False, timeout=60.0) as client:
        # Rebinding scenes needs a session, and the previous experiment may still be settling.
        await wait_until_the_stack_is_usable(
            client, model=args.model, budget_seconds=args.ready_timeout
        )
        session_id = (await client.post("/api/v1/interview/sessions", json={})).json()["id"]
        generated = await client.post(
            f"/api/v1/interview/sessions/{session_id}/questions",
            files={"file": ("cv.pdf", build_resume_pdf(), "application/pdf")},
            data={"count": "2"},
        )
        generated.raise_for_status()
        view = (await client.get(f"/api/v1/interview/sessions/{session_id}/restore")).json()
        answer = {
            "question_no": view["flow"]["current_question_no"],
            "answer": ANSWERS[0],
            "request_id": "v6-crash-1",
        }
        body = await client.post(f"/api/v1/interview/sessions/{session_id}/answers", json=answer)
        body.raise_for_status()
        docker("compose", "stop", "worker")
        finished = await client.post(f"/api/v1/interview/sessions/{session_id}/finish")
        finished.raise_for_status()
        print(f"queued report.summary for {session_id} (worker stopped)")

        claimed = docker(
            "compose", "run", "--rm", "--no-deps", "worker", "python", "-c", CLAIM_SNIPPET
        )
        pending = docker(
            "compose", "exec", "-T", "redis", "redis-cli", "XPENDING", "br:jobs", "br:workers"
        )
        print(claimed.strip().splitlines()[-1] if claimed.strip() else "v6-claimed []")
        print(f"pending before restart: {pending.splitlines()[0] if pending else '0'}")

        started = time.monotonic()
        docker("compose", "start", "worker")
        summary = None
        deadline = time.monotonic() + args.summary_timeout
        while time.monotonic() < deadline:
            await asyncio.sleep(2)
            report = await client.get(f"/api/v1/interview/sessions/{session_id}/report")
            if report.status_code == 200 and report.json().get("summary"):
                summary = report.json()["summary"]
                break
        elapsed = time.monotonic() - started
        remaining = docker(
            "compose", "exec", "-T", "redis", "redis-cli", "XPENDING", "br:jobs", "br:workers"
        )
        print(f"pending after recovery: {remaining.splitlines()[0] if remaining else '0'}")
        print(f"worker restart -> summary written: {elapsed:.1f}s")
        print(f"summary: {summary!r}")
        if summary is None:
            print("FAIL: the reclaimed job never produced a summary")
            return 1
        print("PASS: the crashed consumer's job was reclaimed and completed")
        return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="V6 soak / fault probe (through nginx)")
    sub = parser.add_subparsers(dest="command", required=True)

    soak_parser = sub.add_parser("soak", help="sampled load waves over a long window")
    soak_parser.add_argument("--base", default="http://127.0.0.1:8080")
    soak_parser.add_argument("--duration", type=float, default=1200.0)
    soak_parser.add_argument("--wave-seconds", type=float, default=60.0)
    soak_parser.add_argument("--requests", type=int, default=30)
    soak_parser.add_argument("--concurrency", type=int, default=4)
    soak_parser.add_argument("--json")

    fault_parser = sub.add_parser("fault", help="inject one fault and classify the window")
    fault_parser.add_argument("--base", default="http://127.0.0.1:8080")
    fault_parser.add_argument(
        "--scenario",
        choices=[
            "redis-pause",
            "redis-restart",
            "worker-crash",
            "redis-partition",
            "redis-failover",
        ],
        required=True,
    )
    fault_parser.add_argument("--model", default="smoke-fake")
    fault_parser.add_argument("--summary-timeout", type=float, default=180.0)
    fault_parser.add_argument("--seconds", type=float, default=20.0)
    fault_parser.add_argument("--recovery-timeout", type=float, default=30.0)
    fault_parser.add_argument(
        "--ready-timeout",
        type=float,
        default=120.0,
        help="how long worker-crash waits for the stack to stop answering 503 (P38)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.command == "soak":
        return asyncio.run(soak(args))
    if args.scenario == "worker-crash":
        return asyncio.run(worker_crash(args))
    return asyncio.run(fault(args))


if __name__ == "__main__":
    sys.exit(main())
