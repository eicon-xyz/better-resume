"""V6: soak sampling and fault injection for the distributed pieces.

Everything here talks to the stack through nginx (never straight into a container) and injects
faults with docker, so the evidence is "what a client saw while Redis/worker were broken".

Run it through \`scripts/fault_injection_drill.sh\`, or by hand:

    uv run python -m scripts.fault_probe soak --duration 1200
    uv run python -m scripts.fault_probe fault --scenario redis-pause --seconds 20

P5 的自动 failover 走 --auto（需要 compose 的 drill profile + 应用侧哨兵变量）：

    uv run python -m scripts.fault_probe fault --scenario redis-failover \
        --auto --master-name br-master
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
from dataclasses import dataclass
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
#: P5: the sentinel-managed drill (compose `drill` profile). One sentinel is enough to ask.
SENTINEL_SERVICE = "redis-sentinel-1"
SENTINEL_PORT = "26379"
DEFAULT_MASTER_NAME = "br-master"
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


def parse_sentinel_master(output: str) -> tuple[str, int] | None:
    """`SENTINEL get-master-addr-by-name` 的两行输出 → (host, port)；没主就是 None。

    选举窗口里哨兵回的是空串或 `(nil)`：那是"还没有主"，不是"主没变"，两者不能混。
    """
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if len(lines) < 2 or lines[0].startswith("(") or not lines[1].isdigit():
        return None
    return lines[0], int(lines[1])


def sentinel_master_address(master_name: str = DEFAULT_MASTER_NAME) -> tuple[str, int] | None:
    """问哨兵当前主是谁；哨兵不可用/还没选出主都返回 None（故障窗口里这是正常状态）。"""
    try:
        output = docker(
            "compose",
            "exec",
            "-T",
            SENTINEL_SERVICE,
            "redis-cli",
            "-p",
            SENTINEL_PORT,
            "sentinel",
            "get-master-addr-by-name",
            master_name,
        )
    except RuntimeError:
        return None
    return parse_sentinel_master(output)


def sentinel_switch_line() -> str:
    """哨兵自己打的 +switch-master 日志是"自动提升"最硬的证据；没有就写 none，不编。"""
    try:
        logs = docker("compose", "logs", "--no-log-prefix", "--tail", "200", SENTINEL_SERVICE)
    except RuntimeError:
        return "unavailable"
    for line in logs.splitlines():
        if "+switch-master" in line:
            return line.strip()
    return "none"


def worker_health() -> str:
    try:
        return docker("inspect", "-f", "{{.State.Health.Status}}", service_container("worker"))
    except RuntimeError as exc:
        return f"unknown ({exc})"


def heartbeat_on_new_master(key: str = "br:jobs:health") -> str:
    """worker 的心跳 key 落在被提升的副本上 = 应用的写路径真的切过去了（不只是读能过）。"""
    try:
        return docker("compose", "exec", "-T", "redis-replica", "redis-cli", "exists", key)
    except RuntimeError:
        return "unknown"


def restore_drill_topology(master_name: str = DEFAULT_MASTER_NAME) -> None:
    """恢复动作（必须放 finally）：把原主拉回来，并让哨兵重新发现拓扑。

    单机 compose 的坑：容器重建会换 IP，而哨兵记的是当初解析出来的地址，所以只把容器
    up 回来并不够——三个哨兵各来一次 SENTINEL RESET，让它们按 compose 的主机名重新发现。
    彻底干净的重跑仍然是整体重建：docker compose --profile drill down -v。
    """
    with contextlib.suppress(RuntimeError):
        docker("compose", "up", "-d", "--wait", "redis")
    for index in range(1, 4):
        try_docker(
            "compose",
            "exec",
            "-T",
            f"redis-sentinel-{index}",
            "redis-cli",
            "-p",
            SENTINEL_PORT,
            "sentinel",
            "reset",
            master_name,
        )


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


#: 只有这些结果能证明"故障真的发生了"：429/4xx 只说明应用还活着，不能当证据。
FAULT_OUTCOMES = frozenset({"server_error", "timeout", "transport"})


@dataclass
class AutoFailoverWatch:
    """P5 自动 failover 的判定器：把「何时算自愈 / 何时算超时」从轮询循环里拎出来。

    口径（都落在 `verdict()` 里，**只有 recovered 算通过**）：

    * `ok` 才叫自愈——探针每次都创建会话，200 = 应用真的把写请求打到了可用的主上；
      503 / 超时 / 断连只是噪声，**不许当结束**；
    * 计时从 **kill 那一瞬** 开始（不是从故障窗口结束），超预算算失败；
    * 必须看到哨兵把主换掉（`elected_at`）：应用好了但主没动，是"主没真死"的假通过；
    * 必须至少观测到一次故障：一次都没看到，说明这次 kill 没打成，不构成证据。
    """

    injected_at: float
    budget_seconds: float
    original_master: tuple[str, int] | None = None
    elected_at: float | None = None
    first_ok_at: float | None = None
    saw_fault: bool = False

    def observe_master(self, master: tuple[str, int] | None, *, now: float) -> None:
        """哨兵报出与 kill 前不同的地址 = 提升发生（只记第一次）。"""
        if self.elected_at is not None or master is None:
            return
        if self.original_master is not None and master == self.original_master:
            return
        self.elected_at = now

    def observe_probe(self, outcome: str, *, now: float) -> None:
        if outcome in FAULT_OUTCOMES:
            self.saw_fault = True
        elif outcome == "ok" and self.first_ok_at is None:
            self.first_ok_at = now

    @property
    def recovered(self) -> bool:
        return self.first_ok_at is not None

    @property
    def recovery_ms(self) -> float | None:
        """kill → 首次成功（口径写清：探针自己的超时不算接管耗时，V6 教训）。"""
        if self.first_ok_at is None:
            return None
        return (self.first_ok_at - self.injected_at) * 1000

    @property
    def election_ms(self) -> float | None:
        """kill → 哨兵报出新主；没有提升就是 None。"""
        if self.elected_at is None:
            return None
        return (self.elected_at - self.injected_at) * 1000

    def expired(self, now: float) -> bool:
        return not self.recovered and now - self.injected_at >= self.budget_seconds

    def verdict(self) -> str:
        """recovered / timeout / no-fault-observed / no-promotion；只有第一个算通过。"""
        if not self.recovered:
            return "timeout"
        if not self.saw_fault:
            return "no-fault-observed"
        if self.elected_at is None:
            return "no-promotion"
        return "recovered"


#: verdict → (退出码, 结论文案)。矛盾的结论必须分开说：它们指向完全不同的排查方向。
_FAILOVER_REPORT: dict[str, tuple[int, str]] = {
    "recovered": (0, "PASS: 主挂了之后应用自己切到了新主（没有人工 promotion）"),
    "timeout": (1, "FAIL: 预算内一次成功都没有——自愈没发生（超时算失败，不是「慢」）"),
    "no-promotion": (1, "FAIL: 应用恢复了，但哨兵从没提升过副本——主可能没真死，这不算证据"),
    "no-fault-observed": (1, "FAIL: 一次故障都没观测到——这次 kill 没打成，不构成证据"),
}


def failover_report(verdict: str) -> tuple[int, str]:
    """自动 failover 的结论 → 退出码 + 人话。只有 recovered 是 0。"""
    return _FAILOVER_REPORT.get(verdict, (1, f"FAIL: 未知结论 {verdict!r}"))


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


async def sentinel_failover(args: argparse.Namespace) -> int:
    """P5：kill 主 → 等哨兵自己提升副本 → 应用自己切过去（全程没有人工 promotion）。

    与手工版（--scenario redis-failover）的区别：不建临时副本、不 REPLICAOF NO ONE、
    不改网络别名，只 kill 主，剩下的交给哨兵。前提是 compose 的 drill profile 已经在跑
    （scripts/fault_injection_drill.sh --sentinel 负责 export 两个变量并起栈）。
    """
    master_name = args.master_name
    counts: dict[str, int] = {}
    notes: list[str] = []
    async with httpx.AsyncClient(base_url=args.base, trust_env=False) as client:
        login = await login_with_retry(client)
        # 前置状态必须在故障前就存在：否则 /auth/me 的 401 是"没 cookie"，不是"会话丢了"（P27）。
        cookie = login.cookies.get("br_session")
        original = sentinel_master_address(master_name)
        if original is None:
            print(
                f"FAIL: 哨兵 {SENTINEL_SERVICE} 报不出 {master_name} 的主——drill profile 起了吗？"
            )
            return 2
        print(f"== 哨兵当前主：{original[0]}:{original[1]}")

        injected = time.monotonic()
        watch = AutoFailoverWatch(
            injected_at=injected,
            budget_seconds=args.recovery_timeout,
            original_master=original,
        )
        print(f"== kill 主（docker compose kill redis）；预算 {args.recovery_timeout:g}s")
        try:
            docker("compose", "kill", "redis")
            while True:
                # 先问哨兵再看应用：同一轮里"提升 + 恢复"都发生时，顺序反了会误报 no-promotion。
                watch.observe_master(sentinel_master_address(master_name), now=time.monotonic())
                outcome = await probe_once(client)
                counts[outcome] = counts.get(outcome, 0) + 1
                watch.observe_probe(outcome, now=time.monotonic())
                if watch.recovered or watch.expired(time.monotonic()):
                    break
                await asyncio.sleep(0.2)
        finally:
            # 演练失败也要把拓扑收回来（V6 教训：恢复动作必须在 finally）。
            restore_drill_topology(master_name)

        verdict = watch.verdict()
        code, message = failover_report(verdict)
        print(f"fault window: {json.dumps(dict(sorted(counts.items())), ensure_ascii=False)}")
        if watch.recovery_ms is not None:
            print(f"recovery: kill -> 首次成功 {watch.recovery_ms:.0f} ms（从 kill 那一瞬算）")
        if watch.election_ms is not None:
            print(f"promotion: kill -> 哨兵报出新主 {watch.election_ms:.0f} ms")
        promoted = sentinel_master_address(master_name)
        notes.append(f"verdict={verdict}")
        if promoted is None:
            notes.append("master_after_kill=unknown")
        else:
            notes.append(f"master_after_kill={promoted[0]}:{promoted[1]}")
        if cookie:
            async with httpx.AsyncClient(base_url=args.base, trust_env=False) as old:
                old.cookies.set("br_session", cookie)
                try:
                    me = await old.get("/api/v1/auth/me", timeout=PROBE_TIMEOUT_SECONDS)
                    notes.append(f"old_session_after_failover={me.status_code}")
                except httpx.HTTPError as exc:
                    notes.append(f"old_session_after_failover={type(exc).__name__}")
        notes.append(f"worker_health={worker_health()}")
        notes.append(f"worker_heartbeat_on_new_master={heartbeat_on_new_master()}")
        notes.append(f"sentinel_switch_log={sentinel_switch_line()}")
        print(message)
        for note in notes:
            print(f"note: {note}")
        return code


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
    fault_parser.add_argument(
        "--auto",
        action="store_true",
        help=(
            "redis-failover 专用：只 kill 主，等哨兵自己提升（需要 compose drill profile "
            "与 BR_REDIS_SENTINELS/BR_REDIS_MASTER_NAME），不再人工 promotion"
        ),
    )
    fault_parser.add_argument(
        "--master-name",
        default=DEFAULT_MASTER_NAME,
        help="哨兵监视的主名（compose drill profile 里是 br-master）",
    )
    fault_parser.add_argument("--recovery-timeout", type=float, default=30.0)
    fault_parser.add_argument(
        "--ready-timeout",
        type=float,
        default=120.0,
        help="how long worker-crash waits for the stack to stop answering 503 (P38)",
    )
    args = parser.parse_args(argv)
    if args.command == "fault" and args.auto and args.scenario != "redis-failover":
        # 静默忽略会让人以为跑了自动路径：直接拒绝，别留一条没人跑的分支。
        parser.error("--auto only makes sense with --scenario redis-failover")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.command == "soak":
        return asyncio.run(soak(args))
    if args.scenario == "worker-crash":
        return asyncio.run(worker_crash(args))
    if args.scenario == "redis-failover" and args.auto:
        # P5：走哨兵的自动提升路径（不写 --auto 仍是手工版，weekly 的既有证据不变）。
        return asyncio.run(sentinel_failover(args))
    return asyncio.run(fault(args))


if __name__ == "__main__":
    sys.exit(main())
