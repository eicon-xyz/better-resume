#!/usr/bin/env python3
"""better-resume 系统架构图渲染器（深色「终端蓝图」风格）。

与 docs/audit/MODULE-AUDIT.html 同一条线：渲染产物 + 生成脚本。

* 结构事实来自仓库本身——模块的文件数/行数、HTTP 路由、ORM 表名、Redis 键名、
  LLM 场景与适配器、compose 服务与 profile，全部在渲染时扫描，不写死在模板里。
* 运行状态来自实时探针——docker ps（compose 项目标签）/ TCP / HTTP。探针拿不到
  就写「未知」，绝不编造（AGENTS.md §证据诚实）。
* 单文件产物，无外链、无第三方依赖：python3 直接跑，--watch 就是「实时图」。

用法：
  python3 scripts/build_architecture_map.py                  # 渲染一次（含探针）
  python3 scripts/build_architecture_map.py --no-probe        # 只取仓库事实（不碰 docker/网络）
  python3 scripts/build_architecture_map.py --watch -i 10     # 实时：每 10s 重渲染 + 浏览器自刷
"""

from __future__ import annotations

import argparse
import html
import re
import socket
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "architecture" / "ARCHITECTURE.html"
SRC = ROOT / "apps" / "api" / "src" / "better_resume"
CANVAS_W = 1440
CANVAS_H = 1880
CST = timezone(timedelta(hours=8))
COMPOSE_PROJECT = "better-resume"

# --------------------------------------------------------------------------------------
# 一、仓库事实扫描（纯函数，无副作用）
# --------------------------------------------------------------------------------------


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def py_files(*rels: str) -> list[Path]:
    paths: list[Path] = []
    for rel in rels:
        target = ROOT / rel
        if target.is_file():
            paths.append(target)
        elif target.is_dir():
            paths.extend(sorted(p for p in target.rglob("*.py") if "__pycache__" not in p.parts))
    return paths


def scan_module(*rels: str) -> dict[str, int]:
    files = py_files(*rels)
    return {"files": len(files), "lines": sum(len(read_text(p).splitlines()) for p in files)}


def scan_api_totals() -> dict[str, int]:
    files = py_files("apps/api/src/better_resume")
    return {"files": len(files), "lines": sum(len(read_text(p).splitlines()) for p in files)}


PREFIX_RE = re.compile(r'APIRouter\(\s*prefix="([^"]*)"')
ROUTE_RE = re.compile(r'@router\.(get|post|put|patch|delete|websocket)\(\s*"([^"]*)"')
TABLE_RE = re.compile(r'__tablename__\s*=\s*"([^"]+)"')
KEY_RE = re.compile(r"br:[A-Za-z0-9_:{}.|/-]+")


def scan_routes() -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for path in py_files("apps/api/src/better_resume"):
        text = read_text(path)
        match = PREFIX_RE.search(text)
        prefix = match.group(1) if match else ""
        for method, suffix in ROUTE_RE.findall(text):
            rows.append((method.upper(), f"{prefix}{suffix}"))
    seen: list[tuple[str, str]] = []
    for row in rows:
        if row not in seen:
            seen.append(row)
    return seen


def scan_tables() -> list[str]:
    names: list[str] = []
    for path in py_files("apps/api/src/better_resume"):
        for name in TABLE_RE.findall(read_text(path)):
            if name not in names:
                names.append(name)
    return names


def scan_redis_keys() -> list[str]:
    """扫到的键先按「形状」归一化去重（{xxx} 视作同一占位符），再丢掉被更长键包含的短键。"""
    keys: list[str] = []
    for path in py_files("apps/api/src/better_resume"):
        for raw in KEY_RE.findall(read_text(path)):
            key = raw.rstrip(".,;')")
            if key and key not in keys:
                keys.append(key)
    shapes: dict[str, str] = {}
    for key in sorted(keys):
        shapes.setdefault(re.sub(r"\{[^}]+\}", "{}", key), key)
    kept = sorted(shapes.values())
    return [k for k in kept if not any(other != k and other.startswith(k) for other in kept)]


def scan_scenes() -> list[str]:
    text = read_text(SRC / "llm_gateway" / "scenes.py")
    block = text.split("class LlmScene", 1)[-1].split("SCENE_LABELS", 1)[0]
    return re.findall(r'^\s{4}[A-Z_]+ = "([a-z_]+)"', block, flags=re.MULTILINE)


def scan_adapters(sub: str) -> list[str]:
    directory = SRC / sub / "adapters"
    if not directory.is_dir():
        return []
    return sorted(p.stem for p in directory.glob("*.py") if p.stem != "__init__")


def scan_web() -> dict[str, object]:
    src = ROOT / "apps" / "web" / "src"
    files = [p for p in src.rglob("*") if p.suffix in {".ts", ".tsx"} and p.is_file()]
    lines = sum(len(read_text(p).splitlines()) for p in files)
    pages = sorted(p.stem for p in (src / "pages").glob("*.tsx") if ".test." not in p.name)
    routes = [r for r in re.findall(r'path="([^"]+)"', read_text(src / "App.tsx")) if r != "*"]
    cases = 0
    for path in src.rglob("*.test.ts*"):
        cases += len(re.findall(r"\b(?:it|test)\(", read_text(path)))
    return {"files": len(files), "lines": lines, "pages": pages, "routes": routes, "cases": cases}


def scan_tests() -> dict[str, int]:
    """静态计数：def test_ 出现次数（含参数化用例的每个函数，不等于 pytest 运行时例数）。"""
    total = 0
    for path in py_files("apps/api/tests"):
        total += read_text(path).count("def test_")
    return {"api": total}


def scan_migrations() -> int:
    return len(list((ROOT / "apps/api/migrations/versions").glob("*.py")))


def parse_compose() -> dict[str, dict[str, object]]:
    """极简缩进解析：服务名 / profile / 端口 / healthcheck。不引 PyYAML。

    只认两种 YAML 特性：块内 profiles，以及 <<: *anchor 的合并（哨兵服务靠 <<: *sentinel
    继承 drill profile；不认合并键就会把演练服务算进默认拓扑）。
    """
    text = read_text(ROOT / "compose.yaml")
    services: dict[str, dict[str, object]] = {}
    anchors: dict[str, list[str]] = {}
    in_services = False
    current: str | None = None
    anchor: str | None = None
    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        if indent == 0:
            in_services = stripped.startswith("services:")
            current = None
            found = re.search(r"&(\w[\w-]*)", stripped)
            anchor = found.group(1) if found else None
            if anchor:
                anchors.setdefault(anchor, [])
            continue
        if not in_services:
            if anchor and stripped.startswith("profiles:"):
                anchors[anchor] = re.findall(r'"([^"]+)"', stripped)
            continue
        if indent == 2 and stripped.endswith(":"):
            current = stripped[:-1]
            services[current] = {"profiles": [], "ports": False, "healthcheck": False, "image": ""}
            continue
        if current is None or indent < 4:
            continue
        if stripped.startswith("profiles:"):
            services[current]["profiles"] = re.findall(r'"([^"]+)"', stripped)
        elif stripped.startswith("<<:") and "*" in stripped:
            merged = stripped.rsplit("*", 1)[-1]
            services[current]["profiles"] = list(anchors.get(merged, []))
        elif stripped.startswith("image:") and not services[current]["image"]:
            services[current]["image"] = stripped.split(":", 1)[1].strip()
        elif stripped == "ports:":
            services[current]["ports"] = True
        elif stripped.startswith("healthcheck:"):
            services[current]["healthcheck"] = True
    port = re.search(r"NGINX_PORT:-(\d+)", text)
    if "nginx" in services:
        services["nginx"]["published"] = port.group(1) if port else "?"
    return services


def git_facts() -> dict[str, str]:
    def run(*args: str) -> str:
        try:
            done = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=5)
        except (OSError, subprocess.SubprocessError):
            return ""
        return done.stdout.strip() if done.returncode == 0 else ""

    dirty = run("status", "--porcelain")
    return {
        "sha": run("rev-parse", "--short", "HEAD") or "unknown",
        "branch": run("branch", "--show-current") or "detached",
        "dirty": str(len(dirty.splitlines())) if dirty else "0",
    }


# --------------------------------------------------------------------------------------
# 二、实时探针（docker / TCP / HTTP）——拿不到就标记 unknown，不编造
# --------------------------------------------------------------------------------------


def probe_docker() -> dict[str, dict[str, str]]:
    fmt = '{{.Label "com.docker.compose.service"}}\t{{.State}}\t{{.Status}}'
    cmd = ["docker", "ps", "-a", "--filter", f"label=com.docker.compose.project={COMPOSE_PROJECT}", "--format", fmt]
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"__error__": {"state": "unknown", "detail": f"docker 不可用（{exc.__class__.__name__}）"}}
    if done.returncode != 0:
        return {"__error__": {"state": "unknown", "detail": f"docker ps 退出码 {done.returncode}"}}
    found: dict[str, dict[str, str]] = {}
    for line in done.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        service, state, status = (p.strip() for p in parts)
        found[service] = {"state": state, "detail": status}
    return found


def probe_tcp(port: int, timeout: float = 0.6) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout):
            return True
    except OSError:
        return False


def probe_http(url: str, timeout: float = 1.5) -> tuple[bool, str]:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url, timeout=timeout) as response:
            return True, f"HTTP {response.status}"
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}"
    except urllib.error.URLError:
        return False, "连接失败（端口无应答）"
    except Exception as exc:  # noqa: BLE001 - 探针要把任何失败都变成一行字
        return False, f"{exc.__class__.__name__}（未预期）"


def probe_all(enabled: bool) -> dict[str, object]:
    port = int(str(parse_compose().get("nginx", {}).get("published", 8080) or 8080))
    if not enabled:
        return {"enabled": False, "docker": {}, "tcp": {}, "http": {}, "port": port}
    http: dict[str, tuple[bool, str]] = {
        "edge": probe_http(f"http://127.0.0.1:{port}/healthz"),
        "nginx": probe_http(f"http://127.0.0.1:{port}/nginx-healthz"),
    }
    tcp = {p: probe_tcp(p) for p in (port, 5433, 6379, 5173)}
    return {"enabled": True, "docker": probe_docker(), "tcp": tcp, "http": http, "port": port}


STATE_BADGE = {
    "run": ("run", "● 运行中"),
    "warn": ("warn", "▲ 异常"),
    "progress": ("progress", "◐ 启动中"),
    "stopped": ("stopped", "■ 已停止"),
    "missing": ("missing", "○ 未创建"),
    "done": ("done", "✓ 已完成"),
    "unknown": ("missing", "○ 未知"),
}


def runtime_of(service: str, probe: dict[str, object]) -> tuple[str, str]:
    """把探针结果翻成 badge 类型与一行说明。"""
    docker = probe.get("docker") or {}
    if not probe.get("enabled"):
        return "unknown", "未开探针（--no-probe）"
    if "__error__" in docker:
        return "unknown", str(docker["__error__"]["detail"])
    info = docker.get(service)
    if not info:
        return "missing", "compose 里没有对应容器"
    state = str(info.get("state", ""))
    detail = str(info.get("detail", ""))
    if state == "running":
        if "unhealthy" in detail:
            return "warn", detail
        if "starting" in detail:
            return "progress", detail
        return "run", detail
    if state == "exited":
        return ("done" if "(0)" in detail else "stopped"), detail
    if state in {"created", "paused", "restarting"}:
        return "progress", detail or state
    return "stopped", detail or state


# --------------------------------------------------------------------------------------
# 三、排版模型（坐标手写，内容尽量来自扫描结果）
# --------------------------------------------------------------------------------------


@dataclass
class Node:
    key: str
    x: int
    y: int
    w: int
    h: int
    tone: str
    title: str = ""
    sub: str = ""
    lines: list[str] = field(default_factory=list)
    badge: tuple[str, str] | None = None
    dashed: bool = False
    legend: str = ""


@dataclass
class Wire:
    points: list[tuple[int, int]]
    tone: str
    label: str
    label_at: tuple[int, int] = (0, 0)
    anchor: str = "middle"
    dashed: bool = False
    rotate: bool = False


TONES = {
    "blue": "#79a8ff",
    "cyan": "#5ad1e6",
    "green": "#6fdc8c",
    "amber": "#e8b25d",
    "purple": "#b48cff",
    "red": "#ff7b72",
    "dim": "#7d8590",
}


def esc(text: object) -> str:
    return html.escape(str(text), quote=True)


def fmt(n: int) -> str:
    return f"{n:,}"


def red(text: str) -> str:
    return f'<span class="err">{esc(text)}</span>'


def build_nodes(facts: dict[str, object], probe: dict[str, object]) -> list[Node]:
    mod = facts["modules"]
    routes = facts["routes"]
    tables = facts["tables"]
    keys = facts["keys"]
    scenes = facts["scenes"]
    web = facts["web"]
    tests = facts["tests"]
    migrations = facts["migrations"]
    total = facts["api_totals"]
    compose = facts["compose"]
    nginx_port = str(compose.get("nginx", {}).get("published", "8080"))

    def badge(service: str) -> tuple[str, str]:
        kind, _detail = runtime_of(service, probe)
        return STATE_BADGE[kind][0], STATE_BADGE[kind][1]

    nodes: list[Node] = []

    # ---- 左轨：外部供应商（虚线 = 外部 / 可选） -------------------------------------
    vendor_lines = [
        "<b>DeepSeek 官方</b> · openai 兼容",
        "CHAT / 出题 / 评分 / 追问 / 报告",
        "凭据 BR_DEEPSEEK_API_KEY（.env）",
        "",
        "<b>阿里百炼 DashScope</b> · 第二平台",
        "qwen-plus 文本 · qwen-audio 批量 ASR",
        "paraformer-realtime-v2 实时 ASR",
        "凭据 BR_DASHSCOPE_API_KEY（LLM+ASR 共用）",
        "",
        "<b>讯飞 AST</b> · 流式 ASR",
        "pgs / rg / seg_id 句池归并（移植自旧项目）",
        "",
        "<b>edge-tts</b> · TTS 合成",
        "TtsCache：digest 寻址 mp3",
    ]
    nodes.append(
        Node("vendors", 20, 40, 220, 860, "dim", lines=vendor_lines, dashed=True,
             legend="外部供应商 · 外部依赖")
    )

    # ---- 客户端 ---------------------------------------------------------------------
    web_routes = " · ".join(web["routes"][:6])
    nodes.append(
        Node(
            "web", 600, 40, 470, 132, "blue",
            "web · React 19 + Vite SPA",
            "客户端 · 浏览器（D05/D08）",
            [
                f"路由 {esc(web_routes)}",
                f"{web['files']} 文件 · {fmt(int(web['lines']))} 行 · vitest {web['cases']} 例",
                "api/ 请求层 + SSE/WS 客户端 · audio/ 采集 → PCM → 转写合并（三层合并）",
            ],
            badge=("done", "✓ 已完成"),
        )
    )
    nodes.append(
        Node(
            "contract", 1150, 40, 266, 150, "cyan",
            "契约 · openapi 生成",
            "契约 · 单一事实源（D17）",
            [
                "apps/api/openapi.json",
                "→ openapi-typescript → schema.d.ts",
                "生成物勿手改；契约三件套：",
                "export_openapi → gen:api → extract_api_index",
            ],
            badge=("done", "✓ 已完成"),
        )
    )

    # ---- 边缘 -----------------------------------------------------------------------
    nodes.append(
        Node(
            "nginx", 600, 250, 470, 118, "cyan",
            f"nginx :{nginx_port} · 唯一入口",
            "边缘 · SPA 静态 + /api 反向代理（D07）",
            [
                "upstream 变量 + resolver 127.0.0.11 → --scale api=N 才生效",
                "index.html Cache-Control: no-store · /assets/ immutable",
                "16m 上传上限 · /api/ 关闭缓冲（WS/SSE，read/send 300s）",
            ],
            badge=badge("nginx"),
        )
    )

    # ---- API 单体（模块网格） --------------------------------------------------------
    modules = [
        ("identity", "cyan", "identity", "Cookie session（Redis 30 天滑动）+ WS ticket 一次性握手（D11）"),
        ("http", "cyan", "http", f"REST / WS / SSE 薄层 · {len(routes)} 条路由（/api/v1/*）"),
        ("conversation + chat", "cyan", "conversation+chat", "chat 与 interview 两类会话收敛到一个 conversation 模块（D09）"),
        ("interview_engine", "green", "interview_engine", "双状态机（会话 6 态 / 流程 5 态）· 题级锁 · 热层 · 报告冻结"),
        ("resume_parser", "green", "resume_parser", "pdfplumber + 章节启发式（解析不靠 LLM，D10）"),
        ("llm_gateway", "green", "llm_gateway", f"场景绑定 resolver + 模型注册 + {len(facts['llm_adapters'])} 个 adapter（D04）"),
        ("ai_resilience", "green", "ai_resilience", "单飞（进程内 + 分布式）+ 熔断 + 舱壁 + 超时 + 令牌桶：供应商调用必经"),
        ("media", "purple", "media", "TranscriptionChannel + TtsSynthesizer 两缝 + assembler 句池归并"),
        ("jobs + worker.py", "amber", "jobs+worker.py", "Redis Stream 生产端；worker 进程复用同一模块"),
        ("settings · observability · db", "dim", "settings+observability+db", "BR_ 前缀配置 · structlog + request_id · async 引擎/session"),
    ]
    row_h, row_gap = 58, 8
    col_x = (316, 714)
    row_y0 = 482  # 面板头部 3 行摘要（22px 内边距 + 3×17.6px）之下
    for index, (name, tone, key, desc) in enumerate(modules):
        stat = mod[key]
        col, row = divmod(index, 5)
        nodes.append(
            Node(f"m-{index}", col_x[col], row_y0 + row * (row_h + row_gap), 380, row_h, tone, name, "",
                 [desc, f"{stat['files']} 文件 · {fmt(int(stat['lines']))} 行"])
        )

    api_summary = [
        f"{len(routes)} 条路由 · {len(tables)} 张表 · {migrations} 版迁移 · {total['files']} 文件 / {fmt(int(total['lines']))} 行",
        f"pytest 测试函数 {tests['api']} 个（静态计数）· 只 mock 系统边界（LLM/时钟/Redis/讯飞/音频/IPC）",
        "N 副本无状态：锁 / 热层 / 票据 / 限流桶 / 单飞全在 Redis，写路径失效",
    ]
    nodes.append(
        Node("api", 300, 400, 810, 420, "cyan", badge=badge("api"), lines=api_summary,
             legend="api · FastAPI 模块化单体 :8000 ×N")
    )

    # ---- 运行探针面板 ---------------------------------------------------------------
    probe_lines: list[str] = [
        f"采样 {datetime.now(CST).strftime('%H:%M:%S')}（docker ps + TCP + HTTP）",
        "探针拿不到就写「未知」，不编造状态",
        "",
    ]
    for service in ("postgres", "redis", "migrate", "api", "worker", "nginx"):
        kind, detail = runtime_of(service, probe)
        label = STATE_BADGE[kind][1]
        suffix = f"宿主 :{nginx_port}" if service == "nginx" else ("一次性" if service == "migrate" else "")
        probe_lines.append(f'{esc(service)}  <span class="{kind}">{label}</span>  {esc(suffix)}')
    for service in ("fake-llm", "redis-sentinel-1", "redis-replica"):
        kind, _detail = runtime_of(service, probe)
        profiles = compose.get(service, {}).get("profiles") or []
        joined = " / ".join(profiles) if profiles else "-"
        probe_lines.append(f'{esc(service)}  <span class="{kind}">{STATE_BADGE[kind][1]}</span>  profile {esc(joined)}')
    nodes.append(
        Node("probe", 1150, 400, 266, 420, "dim", lines=probe_lines, dashed=True,
             legend="运行探针 · runtime probe")
    )

    # ---- 异步作业 -------------------------------------------------------------------
    stream = next((k for k in keys if k == "br:jobs"), "br:jobs")
    nodes.append(
        Node(
            "worker", 580, 870, 440, 140, "amber",
            "worker · Redis Stream 消费者",
            "异步 · python -m better_resume.worker",
            [
                f"XREADGROUP {stream} / br:workers → XACK；崩溃接管 XCLAIM(idle≈60s)",
                "心跳 br:worker:heartbeat（TTL）· 死信 br:jobs:dead（兜底 try）",
                "作业 report_summary · 退避 0.5 → 5s（loop_backoff_seconds）",
            ],
            badge=badge("worker"),
        )
    )

    # ---- 数据层 ---------------------------------------------------------------------
    pg_groups = [
        " · ".join(tables[0:3]),
        " · ".join(tables[3:5]),
        " · ".join(tables[5:7]),
        " · ".join(tables[7:]),
    ]
    nodes.append(
        Node(
            "postgres", 290, 1070, 380, 190, "amber",
            "postgres:16 · 5432（内网不发布）",
            "数据 · 关系表 + JSONB + GIN（D03）",
            pg_groups + [f"Alembic {migrations} 版迁移 · volume uploads → /app/data（内容寻址 PDF，多副本共享）"],
            badge=badge("postgres"),
        )
    )
    key_groups = [
        " · ".join(k for k in keys if ":status:" in k or k.endswith(":dead") or k == "br:jobs"),
        " · ".join(k for k in keys if k.startswith("br:lock") or k.startswith("br:hot") or k.startswith("br:ws_ticket")),
        " · ".join(k for k in keys if k.startswith("br:rl") or k.startswith("br:flight")),
        "worker 心跳 br:worker:heartbeat（TTL 30s）",
    ]
    nodes.append(
        Node(
            "redis", 700, 1070, 405, 190, "amber",
            "redis:7 · 6379（内网不发布）",
            "数据 · 会话 / 锁 / 热层 / 票据 / 限流 / 队列",
            key_groups,
            badge=badge("redis"),
        )
    )
    nodes.append(
        Node(
            "drill", 1150, 1070, 266, 190, "amber",
            "drill profile · 哨兵演练",
            "计划 / 可选（默认不启）",
            [
                "redis-sentinel-1/2/3（quorum=2）",
                "redis-replica ×2：主挂时必须仍有可见副本",
                "须同时给 BR_REDIS_SENTINELS + BR_REDIS_MASTER_NAME",
                "演练用 pause 冻结主：kill 会让 compose DNS 失效 → TILT",
            ],
            badge=badge("redis-sentinel-1"), dashed=True,
        )
    )

    # ---- 展开视图：两个深模块 --------------------------------------------------------
    asr = [a for a in facts["asr_adapters"] if a != "edge_tts"]
    tts = [a for a in facts["asr_adapters"] if a == "edge_tts"]
    nodes.append(
        Node("detail", 290, 1320, 1126, 220, "green", dashed=True,
             legend="展开视图 · api 内部两个深模块（虚线 = 展开，不是新进程）")
    )
    nodes.append(
        Node(
            "llm", 310, 1360, 520, 168, "green",
            "llm_gateway · 场景 → 供应商",
            "AI 编排 · 自研轻量（D04，不引 LangChain）",
            [
                f"场景（{len(scenes)}）{' · '.join(scenes)}",
                f"适配器 {' · '.join(facts['llm_adapters'])}",
                "必经 ai_resilience：单飞 + 熔断 + 舱壁 + 超时 + 令牌桶（跨副本共享，降级回进程内）",
                f"缺配置 / 依赖不可用 → {red('503 + Retry-After')} 并点名变量（红色只标错误路径）",
            ],
            badge=("done", "✓ 已完成"),
        )
    )
    nodes.append(
        Node(
            "media", 860, 1360, 536, 172, "purple",
            "media · 语音两缝",
            "语音 · TranscriptionChannel + TtsSynthesizer（D06）",
            [
                "WS /api/v1/media/transcribe：ticket → 音频帧 → replace|archive|final → close(1000)",
                f"ASR 适配器 {' · '.join(asr)}（scripted 为 CI/本地默认）· TTS {tts}",
                "TTS edge_tts + TtsCache → GET /api/v1/media/tts/{digest}.mp3",
                "assembler 句池归并：增量包提交语义（真机证过）",
            ],
            badge=("done", "✓ 已完成"),
        )
    )

    # ---- 验证网 ---------------------------------------------------------------------
    nodes.append(Node("verify", 290, 1650, 1126, 170, "cyan",
                      legend="验证网 · scripts/verify.sh 单一入口（CI 与本地同一份命令）"))
    nodes.append(Node("verify-ci", 310, 1690, 340, 110, "cyan", "CI · GitHub Actions 双 job", "", [
        "backend：ruff + pytest + alembic check",
        "frontend：eslint + tsc + vitest",
        "nightly.yml · weekly-full.yml（长跑 / 浸泡）",
    ]))
    nodes.append(Node("verify-layers", 670, 1690, 340, 110, "cyan", "verify.sh · 分层", "", [
        "unit · contract · coverage · deploy",
        "fault · soak · real · scripts · all",
        "real 层带预算守卫 BR_REAL_CALL_BUDGET=200",
    ]))
    nodes.append(Node("verify-drills", 1030, 1690, 366, 110, "cyan", "演练与证明", "", [
        "compose_smoke.sh（REST/SSE/WS/双实例/心跳）",
        "kill_instance_drill.sh · fault_injection_drill.sh",
        "verify_mutation.sh（基线绿 → 变异红 → 恢复绿）",
    ]))

    # ---- 本机开发环境（实时 TCP 探针） ----------------------------------------------
    tcp = probe.get("tcp") or {}

    def tcp_line(port: int, label: str) -> str:
        if not probe.get("enabled"):
            return f"{label} ○ 未探针"
        ok = tcp.get(port)
        klass = "run" if ok else "missing"
        text = "● 监听中" if ok else "○ 未启动"
        return f'{label} <span class="{klass}">{text}</span>'

    nodes.append(
        Node("devenv", 20, 930, 220, 172, "dim", "本机开发环境", "探针 · TCP", [
            tcp_line(5433, "postgres:5433"),
            tcp_line(6379, "redis:6379"),
            tcp_line(int(nginx_port), f"nginx:{nginx_port}"),
            "uv .venv ✓ · pnpm node_modules ✓",
            "compose 内网 5432/6379 不发布",
        ])
    )
    return nodes


def build_wires() -> list[Wire]:
    return [
        Wire([(835, 174), (835, 244)], "blue", "fetch · EventSource(SSE) · WebSocket", (900, 210), "start"),
        Wire([(835, 370), (835, 394)], "cyan", "proxy_pass $api_upstream$request_uri（/api/）", (852, 384), "start"),
        Wire([(1110, 520), (1130, 520), (1130, 105), (1146, 105)], "cyan", "openapi.json 导出", (1130, 330), "middle", rotate=True),
        Wire([(1283, 190), (1283, 226), (900, 226), (900, 178)], "cyan", "生成 · 契约三件套校验", (1283, 310), "middle", dashed=True, rotate=True),
        Wire([(400, 822), (400, 1064)], "amber", "SQL · asyncpg（统一 get_session）", (410, 848), "start"),
        Wire([(1090, 822), (1090, 1064)], "amber", "锁 / 热层 / 票据 / 限流桶 / 单飞 · XADD br:jobs", (1080, 1046), "end"),
        Wire([(1020, 950), (1045, 950), (1045, 1064)], "amber", "XREADGROUP → XACK · 接管 XCLAIM(idle)", (1054, 996), "start", dashed=True),
        Wire([(620, 1012), (620, 1064)], "amber", "写报告 / 作业状态", (630, 1046), "start"),
        Wire([(300, 760), (275, 760), (275, 600), (243, 600)], "green", "HTTPS · OpenAI 兼容（必经 ai_resilience）", (275, 680), "middle", rotate=True),
        Wire([(300, 800), (255, 800), (255, 1420), (286, 1420)], "dim", "展开（不是新进程）", (255, 1110), "middle", dashed=True, rotate=True),
        Wire([(600, 1542), (600, 1600), (248, 1600), (248, 903)], "purple", "ASR/TTS 出网（WSS / HTTPS）", (430, 1594), "middle", dashed=True),
        Wire([(1150, 780), (1135, 780), (1135, 700), (1114, 700)], "dim", "探针", (1135, 741), "middle", dashed=True, rotate=True),
    ]


# --------------------------------------------------------------------------------------
# 四、渲染
# --------------------------------------------------------------------------------------

CSS = """
:root{
  --bg:#0b0f14; --fg:#c9d1d9; --dim:#7d8590; --hair:#3a4450;
  --blue:#79a8ff; --cyan:#5ad1e6; --green:#6fdc8c; --amber:#e8b25d; --purple:#b48cff; --red:#ff7b72;
  --mono:"JetBrains Mono","SF Mono",Menlo,Consolas,"Liberation Mono","DejaVu Sans Mono",monospace;
}
/* 图层色：每个节点带一个 tone class，边框 / 副标题 / 面板图例都取它；
   没有这段，var(--tone) 会退化成 currentColor，边框全变灰。 */
.blue{--tone:var(--blue)} .cyan{--tone:var(--cyan)} .green{--tone:var(--green)}
.amber{--tone:var(--amber)} .purple{--tone:var(--purple)} .red{--tone:var(--red)} .dim{--tone:var(--dim)}
*{box-sizing:border-box}
html,body{margin:0;padding:0;background:var(--bg);color:var(--fg);
  font-family:var(--mono);font-size:13px;line-height:1.45;-webkit-font-smoothing:antialiased}
.page{width:1480px;margin:0 auto;padding:22px 20px 40px}
.masthead{text-align:center;padding:6px 0 14px;border-bottom:1px solid var(--hair)}
.masthead h1{margin:0;font-size:15px;letter-spacing:.14em;color:#fff;font-weight:700}
.masthead h1 .dot{color:var(--dim);padding:0 8px}
.masthead .sub{margin-top:6px;font-size:11px;color:var(--dim);letter-spacing:.06em}
.masthead .meta{margin-top:8px;font-size:11px;color:var(--dim)}
.masthead .meta b{color:var(--fg);font-weight:400}
.live{display:inline-block;min-width:150px;text-align:left}
.live.ok{color:var(--green)}
.live.dim{color:var(--dim)}
.legend{display:flex;flex-wrap:wrap;gap:6px 22px;padding:10px 2px;border-bottom:1px solid var(--hair);font-size:11px;color:var(--dim)}
.legend .grp{display:flex;gap:14px;align-items:center}
.legend .sw{display:inline-flex;align-items:center;gap:6px;color:var(--fg);white-space:nowrap}
.legend .sw i{width:16px;height:9px;border:1px solid currentColor;display:inline-block}
.legend .sw.dashed i{border-style:dashed}
.legend .bd{color:var(--fg);display:inline-flex;gap:5px;align-items:center;white-space:nowrap}
.canvas{position:relative;width:1440px;height:1880px;margin:14px auto 0}
svg.wires{position:absolute;left:0;top:0;overflow:visible}
svg.wires path{fill:none;stroke-width:1}
svg.wires path.dashed{stroke-dasharray:4 3}
.wl{font-family:var(--mono);font-size:10px;fill:var(--dim);paint-order:stroke;stroke:var(--bg);stroke-width:3px;stroke-linejoin:round}
.box{position:absolute;border:1px solid var(--tone);background:var(--bg)}
.box.dashed{border-style:dashed}
.box .pad{padding:9px 11px}
.box .t,.panel .t{color:#fff;font-weight:700;font-size:13px}
.box .s,.panel .s{color:var(--tone);font-size:11px;margin-top:2px}
.box .l,.panel .l{color:var(--dim);font-size:11px;line-height:1.6;margin-top:5px;white-space:pre-wrap;word-break:break-word}
.box .l b,.panel .l b{color:var(--fg);font-weight:400}
.box .err,.panel .err{color:var(--red)}
.box .l .run,.panel .l .run{color:var(--green)}
.box .l .missing,.panel .l .missing{color:var(--dim)}
.panel .pad{padding:22px 12px 9px}
.mod .n{white-space:nowrap}
.panel{position:absolute;border:1px solid var(--tone);background:var(--bg)}
.panel.dashed{border-style:dashed}
.panel>.plegend{position:absolute;top:-8px;left:12px;background:var(--bg);padding:0 6px;font-size:11px;color:var(--tone);white-space:nowrap}
.badge{position:absolute;top:-8px;right:10px;background:var(--bg);padding:0 5px;font-size:11px;white-space:nowrap}
.badge.run{color:var(--green);animation:softpulse 2.4s ease-in-out infinite}
.badge.done{color:var(--green)}
.badge.warn{color:var(--red)}
.badge.progress{color:var(--blue)}
.badge.stopped,.badge.missing{color:var(--dim)}
@keyframes softpulse{0%,100%{opacity:1}50%{opacity:.35}}
@media (prefers-reduced-motion:reduce){.badge.run{animation:none}}
.mod{position:absolute;border:1px solid var(--hair);padding:5px 9px}
.mod .n{color:var(--tone);font-weight:700;font-size:12px}
.mod .d{color:var(--dim);font-size:11px;line-height:1.35}
.mod .f{position:absolute;top:5px;right:9px;color:var(--dim);font-size:10px}
.mods .mod .n{color:var(--tone)}
.log{margin-top:26px;border:1px solid var(--hair);padding:18px 14px 12px;position:relative}
.log>.plegend{background:var(--bg);color:var(--dim)}
.log table{width:100%;border-collapse:collapse;font-size:11px}
.log td{padding:2px 10px 2px 0;color:var(--dim);white-space:nowrap;vertical-align:top}
.log td.t{color:#4d5866;width:74px}
.log td.s{color:var(--fg);width:86px}
.log td.b{width:96px}
.log td.d{white-space:normal}
.log .run,.log .done{color:var(--green)}
.log .warn{color:var(--red)}
.log .progress{color:var(--blue)}
.log .stopped,.log .missing{color:var(--dim)}
.cmd{margin-top:10px;padding-top:8px;border-top:1px dashed var(--hair);font-size:11px;color:var(--dim)}
.cmd .p{color:var(--green)}
.tools{margin-top:14px;display:flex;gap:14px;align-items:center;font-size:11px;color:var(--dim)}
.tools button{font-family:var(--mono);font-size:11px;color:var(--fg);background:var(--bg);border:1px solid var(--hair);padding:3px 9px;cursor:pointer}
.tools button:hover{border-color:var(--dim)}
.foot{margin-top:14px;font-size:11px;color:var(--dim);border-top:1px solid var(--hair);padding-top:10px;line-height:1.7}
.foot code{color:var(--fg)}
"""

SCRIPT = """
(function () {
  var PORT = __PORT__;
  var BASE = "http://127.0.0.1:" + PORT;
  var PERIOD = __PERIOD__;
  var clock = document.getElementById("clock");
  var live = document.getElementById("live");
  var btn = document.getElementById("autoreload");
  function tick() { clock.textContent = new Date().toLocaleTimeString("zh-CN", { hour12: false }); }
  tick(); setInterval(tick, 1000);
  // no-cors 读不到状态码：只能证明这个端口上有人应答，所以文案只写可达性，不写健康。
  function ping() {
    fetch(BASE + "/healthz", { mode: "no-cors", cache: "no-store" }).then(function () {
      live.textContent = "● 边缘可达 :" + PORT; live.className = "live ok";
    }).catch(function () {
      live.textContent = "○ 快照（未探测到边缘）"; live.className = "live dim";
    });
  }
  ping(); setInterval(ping, PERIOD);
  var timer = null;
  function toggle() {
    if (timer) { clearInterval(timer); timer = null; btn.textContent = "自动刷新：关"; }
    else { timer = setInterval(function () { location.reload(); }, PERIOD); btn.textContent = "自动刷新：开"; }
  }
  btn.addEventListener("click", toggle);
  if (new URLSearchParams(location.search).get("auto") === "1") { toggle(); }
})();
"""


def render_box(node: Node) -> str:
    classes = ["box", node.tone] + (["dashed"] if node.dashed else [])
    style = f"left:{node.x}px;top:{node.y}px;width:{node.w}px;height:{node.h}px"
    parts = [f'<div class="{" ".join(classes)}" style="{style}">']
    if node.badge:
        parts.append(f'<span class="badge {node.badge[0]}">{esc(node.badge[1])}</span>')
    parts.append('<div class="pad">')
    if node.title:
        parts.append(f'<div class="t">{esc(node.title)}</div>')
    if node.sub:
        parts.append(f'<div class="s">{esc(node.sub)}</div>')
    if node.lines:
        parts.append('<div class="l">' + "\n".join(node.lines) + "</div>")
    parts.append("</div></div>")
    return "".join(parts)


def render_panel(node: Node) -> str:
    classes = ["panel", node.tone] + (["dashed"] if node.dashed else [])
    style = f"left:{node.x}px;top:{node.y}px;width:{node.w}px;height:{node.h}px"
    parts = [f'<div class="{" ".join(classes)}" style="{style}">']
    if node.legend:
        parts.append(f'<div class="plegend">{node.legend}</div>')
    if node.badge:
        parts.append(f'<span class="badge {node.badge[0]}">{esc(node.badge[1])}</span>')
    parts.append('<div class="pad">')
    if node.title:
        parts.append(f'<div class="t">{esc(node.title)}</div>')
    if node.sub:
        parts.append(f'<div class="s">{esc(node.sub)}</div>')
    if node.lines:
        parts.append('<div class="l">' + "\n".join(node.lines) + "</div>")
    parts.append("</div></div>")
    return "".join(parts)


def render_mod(node: Node) -> str:
    desc, files = node.lines[0], node.lines[1]
    style = f"left:{node.x}px;top:{node.y}px;width:{node.w}px;height:{node.h}px"
    return (
        f'<div class="mod" style="{style}">'
        f'<div class="n" style="color:{TONES[node.tone]}">{esc(node.title)}</div>'
        f'<div class="f">{esc(files)}</div>'
        f'<div class="d">{esc(desc)}</div></div>'
    )


def render_wire(wire: Wire) -> str:
    path = "M " + " L ".join(f"{x} {y}" for x, y in wire.points)
    klass = "dashed" if wire.dashed else ""
    color = TONES[wire.tone]
    out = [f'<path class="{klass}" d="{path}" stroke="{color}" marker-end="url(#ah-{wire.tone})"/>']
    for x, y in wire.points[1:-1]:
        out.append(f'<circle cx="{x}" cy="{y}" r="2" fill="{color}"/>')
    lx, ly = wire.label_at
    transform = f' transform="rotate(-90 {lx} {ly})"' if wire.rotate else ""
    out.append(f'<text class="wl" x="{lx}" y="{ly}" text-anchor="{wire.anchor}"{transform}>{esc(wire.label)}</text>')
    return "".join(out)


def render_markers() -> str:
    out = []
    for tone, color in TONES.items():
        out.append(
            f'<marker id="ah-{tone}" viewBox="0 0 8 8" refX="7.2" refY="4" markerWidth="6" markerHeight="6" '
            f'orient="auto"><path d="M 0 0.6 L 7.6 4 L 0 7.4 z" fill="{color}"/></marker>'
        )
    return "".join(out)


def render_log(facts: dict[str, object], probe: dict[str, object]) -> str:
    compose = facts["compose"]
    now = datetime.now(CST)
    period = int(probe.get("period", 5))
    rows: list[str] = []
    for offset, service in enumerate(("nginx", "api", "worker", "postgres", "redis", "migrate")):
        stamp = (now - timedelta(seconds=offset)).strftime("%H:%M:%S")
        kind, detail = runtime_of(service, probe)
        label = STATE_BADGE[kind][1]
        if service == "nginx":
            _ok, text = (probe.get("http") or {}).get("nginx", (False, "未探针"))
            detail = f"GET /nginx-healthz → {text}"
        elif service == "api":
            _ok, text = (probe.get("http") or {}).get("edge", (False, "未探针"))
            detail = f"GET /healthz（穿 nginx）→ {text}"
        elif service == "worker":
            detail = "心跳 br:worker:heartbeat · " + detail
        elif service == "migrate":
            detail = "alembic upgrade head（一次性）· " + detail
        rows.append(
            f'<tr><td class="t">{stamp}</td><td class="s">{esc(service)}</td>'
            f'<td class="b {kind}">{label}</td><td class="d">{esc(detail)}</td></tr>'
        )
    if probe.get("enabled"):
        tcp = probe.get("tcp") or {}
        for port, label in ((5433, "postgres:5433 原生测试库"), (6379, "redis:6379 原生测试库")):
            ok = tcp.get(port)
            rows.append(
                f'<tr><td class="t">{now.strftime("%H:%M:%S")}</td><td class="s">host</td>'
                f'<td class="b {"run" if ok else "missing"}">{"● 监听中" if ok else "○ 未启动"}</td>'
                f'<td class="d">TCP 127.0.0.1:{port} · {esc(label)}</td></tr>'
            )
    head = (
        '<div class="log">'
        f'<div class="plegend">session log · 探针事件 · 每 {period}s 采样一次，状态变化时记录</div>'
    )
    base_services = [s for s in compose if not compose[s].get("profiles")]
    up = sum(1 for s in base_services if runtime_of(str(s), probe)[0] == "run")
    names = " · ".join(("nginx", "api", "worker", "postgres", "redis", "migrate"))
    foot = (
        '<div class="cmd"><span class="p">~/better-resume $</span> docker compose ps'
        f'<div>● 探针 {now.strftime("%H:%M:%S")} · {up}/{len(base_services)} 运行中 [{esc(names)}] · '
        "profile 服务（smoke / drill）默认不启</div></div>"
    )
    return head + "<table>" + "".join(rows) + "</table>" + foot + "</div>"


def render(facts: dict[str, object], probe: dict[str, object]) -> str:
    nodes = build_nodes(facts, probe)
    wires = build_wires()
    generated = datetime.now(CST)
    git = facts["git"]
    period = int(probe.get("period", 5))
    panel_keys = {"vendors", "api", "probe", "detail", "verify"}

    svg = (
        f'<svg class="wires" width="{CANVAS_W}" height="{CANVAS_H}" viewBox="0 0 {CANVAS_W} {CANVAS_H}">'
        f"<defs>{render_markers()}</defs>" + "".join(render_wire(w) for w in wires) + "</svg>"
    )
    panels = "".join(render_panel(n) for n in nodes if n.key in panel_keys)
    mods = "".join(render_mod(n) for n in nodes if n.key.startswith("m-"))
    boxes = "".join(render_box(n) for n in nodes if n.key not in panel_keys and not n.key.startswith("m-"))
    canvas = f'<div class="canvas">{svg}{panels}{mods}{boxes}</div>'

    badge_legend = "".join(
        f'<span class="bd {kind}">{esc(label)}</span>'
        for kind, label in (
            ("run", "● 运行中"), ("warn", "▲ 异常"), ("progress", "◐ 进行中"),
            ("stopped", "■ 已停止"), ("missing", "○ 未创建"), ("done", "✓ 已完成"),
        )
    )
    tone_legend = "".join(
        f'<span class="sw {cls}" style="color:{TONES[tone]}"><i></i>{esc(label)}</span>'
        for tone, label, cls in (
            ("blue", "客户端", ""), ("cyan", "边缘 / 接入", ""), ("green", "AI 与韧性", ""),
            ("amber", "数据与异步", ""), ("purple", "语音与媒体", ""),
            ("dim", "外部依赖（虚线 = 计划 / 可选）", "dashed"),
        )
    )
    script = SCRIPT.replace("__PORT__", str(probe.get("port", 8080))).replace("__PERIOD__", str(max(period, 5) * 1000))
    stamp = generated.strftime("%Y-%m-%d %H:%M:%S %z")

    head = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=1480"/>
<title>better-resume · 系统架构</title>
<style>{CSS}</style>
</head>
<body>
<div class="page">
<div class="masthead">
  <h1>BETTER-RESUME<span class="dot">·</span>系统架构<span class="dot">·</span>FastAPI 主导<span class="dot">·</span>Redis Stream 异步作业</h1>
  <div class="sub">深色终端蓝图 · 结构事实扫描自仓库 · 运行状态来自实时探针（docker ps / TCP / HTTP）</div>
  <div class="meta">
    <span id="live" class="live dim">○ 快照</span>
    <b>时钟 <span id="clock">--:--:--</span></b> · 渲染 <b>{stamp}</b> ·
    HEAD <b>{esc(git["sha"])}</b> @ <b>{esc(git["branch"])}</b>（未提交 {esc(git["dirty"])} 项）·
    探针 {"开" if probe.get("enabled") else "关（--no-probe）"} · 采样 {period}s
  </div>
</div>
<div class="legend">
  <span class="grp">{tone_legend}</span>
  <span class="grp">{badge_legend}</span>
  <span class="grp"><span class="sw">── 同步调用</span><span class="sw dashed"><i></i>异步 / 展开</span></span>
</div>
"""
    tail = f"""
<div class="tools">
  <button id="autoreload">自动刷新：关</button>
  <span>配合 <code>python3 scripts/build_architecture_map.py --watch -i {period}</code> 使用：脚本重渲染，页面自动重载；
  也可在地址后加 <code>?auto=1</code> 直接开启。</span>
</div>
<div class="foot">
  生成脚本 <code>scripts/build_architecture_map.py</code> · 产物 <code>docs/architecture/ARCHITECTURE.html</code> ·
  手改 HTML 会在下一次渲染被覆盖：结构变化改脚本，状态变化不用改（探针自动读）。
</div>
</div>
<script>{script}</script>
</body>
</html>
"""
    return head + canvas + render_log(facts, probe) + tail



def check_layout(nodes: list[Node], wires: list[Wire]) -> list[str]:
    """排版自检：盒子不重叠（父子包含除外）、连线不穿盒、全部落在画布内。

    坐标是手写的，改布局最容易犯的就是这三类错；--check 把它们变成退出码。
    """
    rects = {n.key: (n.x, n.y, n.x + n.w, n.y + n.h) for n in nodes}
    problems: list[str] = []

    def contains(outer: tuple[int, int, int, int], inner: tuple[int, int, int, int]) -> bool:
        return outer[0] <= inner[0] and outer[1] <= inner[1] and outer[2] >= inner[2] and outer[3] >= inner[3]

    keys = sorted(rects)
    for index, first in enumerate(keys):
        for second in keys[index + 1:]:
            a, b = rects[first], rects[second]
            if contains(a, b) or contains(b, a):
                continue
            if a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]:
                problems.append(f"盒子重叠：{first} {a} × {second} {b}")

    def inside(point: tuple[int, int], rect: tuple[int, int, int, int], pad: int) -> bool:
        x, y = point
        return rect[0] - pad <= x <= rect[2] + pad and rect[1] - pad <= y <= rect[3] + pad

    for wire in wires:
        for start, end in zip(wire.points, wire.points[1:]):
            if start[0] != end[0] and start[1] != end[1]:
                problems.append(f"连线非正交：{wire.label} {start}->{end}")
                continue
            for key, rect in rects.items():
                if inside(start, rect, 3) or inside(end, rect, 3):
                    continue
                if start[0] == end[0]:
                    low, high = sorted((start[1], end[1]))
                    hit = rect[0] < start[0] < rect[2] and low < rect[3] and high > rect[1]
                else:
                    low, high = sorted((start[0], end[0]))
                    hit = rect[1] < start[1] < rect[3] and low < rect[2] and high > rect[0]
                if hit:
                    problems.append(f"连线穿盒：{wire.label} {start}->{end} 穿过 {key} {rect}")

    for key, rect in rects.items():
        if rect[0] < 0 or rect[1] < 0 or rect[2] > CANVAS_W or rect[3] > CANVAS_H:
            problems.append(f"超出画布：{key} {rect}（画布 {CANVAS_W}x{CANVAS_H}）")
    return problems


# --------------------------------------------------------------------------------------
# 五、入口
# --------------------------------------------------------------------------------------


MODULE_TARGETS = {
    "identity": ("identity",),
    "http": ("http",),
    "conversation+chat": ("conversation", "chat"),
    "interview_engine": ("interview_engine",),
    "resume_parser": ("resume_parser",),
    "llm_gateway": ("llm_gateway",),
    "ai_resilience": ("ai_resilience",),
    "media": ("media",),
    "jobs+worker.py": ("jobs", "worker.py"),
    "settings+observability+db": ("settings", "observability", "db"),
}


def gather(probe_enabled: bool, period: int) -> tuple[dict[str, object], dict[str, object]]:
    modules = {
        name: scan_module(*(f"apps/api/src/better_resume/{rel}" for rel in rels))
        for name, rels in MODULE_TARGETS.items()
    }
    facts: dict[str, object] = {
        "modules": modules,
        "routes": scan_routes(),
        "tables": scan_tables(),
        "keys": scan_redis_keys(),
        "scenes": scan_scenes(),
        "llm_adapters": scan_adapters("llm_gateway"),
        "asr_adapters": scan_adapters("media"),
        "web": scan_web(),
        "tests": scan_tests(),
        "migrations": scan_migrations(),
        "api_totals": scan_api_totals(),
        "compose": parse_compose(),
        "git": git_facts(),
    }
    probe = probe_all(probe_enabled)
    probe["period"] = period
    return facts, probe


def render_once(out: Path, probe_enabled: bool, period: int) -> str:
    facts, probe = gather(probe_enabled, period)
    page = render(facts, probe)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(page, encoding="utf-8")
    tmp.replace(out)
    compose = facts["compose"]
    base = [s for s in compose if not compose[s].get("profiles")]
    up = sum(1 for s in base if runtime_of(str(s), probe)[0] == "run")
    summary = (
        f"[{datetime.now(CST).strftime('%H:%M:%S')}] {out.name} 已渲染 · {len(page) // 1024} KB · "
        f"模块 {len(facts['modules'])} · 路由 {len(facts['routes'])} · 表 {len(facts['tables'])} · "
        f"键 {len(facts['keys'])} · compose {up}/{len(base)} 运行中"
    )
    print(summary, flush=True)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="渲染 better-resume 系统架构图（单文件 HTML，深色终端蓝图风格）")
    parser.add_argument("--out", default=str(OUT), help="输出路径（默认 docs/architecture/ARCHITECTURE.html）")
    parser.add_argument("--no-probe", action="store_true", help="不跑 docker/TCP/HTTP 探针，只渲染仓库事实")
    parser.add_argument("--watch", action="store_true", help="循环重渲染（实时图；配合页面自动刷新）")
    parser.add_argument("-i", "--interval", type=int, default=5, help="--watch 的重渲染间隔秒数（默认 5）")
    parser.add_argument("--check", action="store_true", help="只做排版自检（不写文件）：重叠 / 穿盒 / 越界")
    args = parser.parse_args()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if args.check:
        facts, probe = gather(not args.no_probe, args.interval)
        problems = check_layout(build_nodes(facts, probe), build_wires())
        for problem in problems:
            print("  " + problem)
        print(f"排版自检：{'FAIL' if problems else 'PASS'}（{len(problems)} 处问题）", flush=True)
        return 1 if problems else 0
    if not args.watch:
        render_once(out, not args.no_probe, args.interval)
        return 0
    while True:
        render_once(out, not args.no_probe, args.interval)
        time.sleep(max(args.interval, 2))


if __name__ == "__main__":
    raise SystemExit(main())


