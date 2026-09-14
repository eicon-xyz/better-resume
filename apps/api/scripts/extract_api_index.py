"""Generate the API index skill from the OpenAPI document plus the web routes (M6-T7).

    uv run --project apps/api python apps/api/scripts/extract_api_index.py
    uv run --project apps/api python apps/api/scripts/extract_api_index.py --check

The ticket writes this path as scripts/extract_api_index.py; in this repo it lives next to
export_openapi.py, i.e. apps/api/scripts/extract_api_index.py, and runs with the api project.

openapi.json itself is drift-checked, so the endpoint table cannot fall behind the code; the
frontend routes and the consumer column are read from apps/web/src at generation time. The
generated file is never edited by hand: CI runs --check.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]  # apps/api/scripts -> repo root
OPENAPI = REPO_ROOT / "apps/api/openapi.json"
APP_TSX = REPO_ROOT / "apps/web/src/App.tsx"
WEB_SRC = REPO_ROOT / "apps/web/src"
TARGET = REPO_ROOT / "skills/api-index/generated-api-index.md"

#: Endpoints that do not require a session cookie. Kept explicit on purpose: the generated
#: document would otherwise need per-route security metadata that we do not emit yet.
PUBLIC_PATHS = {"/healthz", "/api/v1/auth/session", "/api/v1/auth/ws-ticket", "/api/v1/models"}

#: WebSockets never appear in OpenAPI, so the index keeps them here.
WEBSOCKETS = [("/api/v1/media/transcribe", "实时转写（一次性 ticket 握手）", "ticket")]

#: Idempotency cannot be read off the HTTP method alone. Everything else is derived: the two
#: keyed POSTs carry their dedupe key in the body, and these two are state-machine writes that
#: replay (questions) or freeze a snapshot (finish) instead of writing twice.
IDEMPOTENCY_HINTS = {
    ("post", "/api/v1/interview/sessions/{session_id}/questions"): "幂等（已出题回放；生成中 409）",
    ("post", "/api/v1/interview/sessions/{session_id}/finish"): "幂等（报告冻结后回放快照）",
}

API_PATH_IN_SOURCE = re.compile(r"/api/v1/[A-Za-z0-9_\-/{}$.:]*")
PARAM_IN_SOURCE = re.compile(r"\$\{[^}]*\}")
PARAM_IN_TEMPLATE = re.compile(r"\{[^}]*\}")
ROUTE_IN_APP = re.compile(r'<Route\s+path="([^"]+)"\s+element=\{<([A-Za-z0-9_]+)')
NAVIGATE_TARGET = re.compile(r'to="([^"]+)"')


def _normal_form(text: str) -> str:
    """Collapse a template placeholder and an OpenAPI placeholder into the same token."""
    return PARAM_IN_SOURCE.sub("{p}", text)


def _template_form(path: str) -> str:
    return PARAM_IN_TEMPLATE.sub("{p}", path)


def _consumes(candidate: str, path: str) -> bool:
    """True when a source literal points at path (exact, or a literal prefix of it)."""
    template = _template_form(path)
    if candidate == template:
        return True
    head, _, tail = template.rpartition("/")
    # ".../scenes/" + encodeURIComponent(scene) is the only truncated form we accept; a plain
    # collection literal (".../media/tts") must not claim the item endpoint next to it.
    return "{" in tail and candidate == head + "/"


def frontend_consumers(paths: list[str]) -> dict[str, list[str]]:
    """Map each API path to the web source files that reference it."""
    consumers: dict[str, list[str]] = {path: [] for path in paths}
    for file in sorted(WEB_SRC.rglob("*.ts*")):
        if ".test." in file.name or file.name == "schema.d.ts":
            continue
        text = file.read_text(encoding="utf-8")
        found = {_normal_form(match) for match in API_PATH_IN_SOURCE.findall(text)}
        relative = str(file.relative_to(WEB_SRC))
        for path in dict.fromkeys(paths):
            if any(_consumes(candidate, path) for candidate in found):
                consumers[path].append(relative)
    return consumers


def _component_file(component: str) -> str | None:
    pattern = re.compile(r"export\s+(?:default\s+)?function\s+" + re.escape(component) + r"\b")
    for file in sorted(WEB_SRC.rglob("*.tsx")):
        if ".test." in file.name:
            continue
        if pattern.search(file.read_text(encoding="utf-8")):
            return str(file.relative_to(WEB_SRC))
    return None


def frontend_routes() -> list[tuple[str, str]]:
    """Read the SPA routes from App.tsx: (path, page component or redirect)."""
    routes: list[tuple[str, str]] = []
    for line in APP_TSX.read_text(encoding="utf-8").splitlines():
        match = ROUTE_IN_APP.search(line)
        if match is None:
            continue
        path, component = match.groups()
        if component == "Navigate":
            target = NAVIGATE_TARGET.search(line)
            label = "Navigate -> " + (target.group(1) if target else "?")
        else:
            file = _component_file(component)
            label = component if file is None else component + "（" + file + "）"
        routes.append((path, label))
    return routes


def _body_properties(document: dict, operation: dict) -> set[str]:
    schema = operation.get("requestBody", {}).get("content", {}).get("application/json", {})
    schema = schema.get("schema", {})
    if "$ref" in schema:
        name = schema["$ref"].rsplit("/", maxsplit=1)[-1]
        schema = document.get("components", {}).get("schemas", {}).get(name, {})
    return set(schema.get("properties", {}))


def idempotency_for(method: str, path: str, body: set[str]) -> str:
    hint = IDEMPOTENCY_HINTS.get((method, path))
    if hint is not None:
        return hint
    if method in {"get", "put", "delete"}:
        return "天然幂等"
    if "request_id" in body:
        return "幂等键 request_id"
    if "client_message_id" in body:
        return "幂等键 client_message_id"
    return "非幂等"


def _cell(items: list[str]) -> str:
    return ", ".join("\u0060" + item + "\u0060" for item in items) if items else "—"


def render() -> str:
    document = json.loads(OPENAPI.read_text(encoding="utf-8"))
    operations = [
        (method, path, operation)
        for path, methods in document["paths"].items()
        for method, operation in methods.items()
    ]
    operations.sort(key=lambda item: (item[1], item[0]))
    ws_paths = [path for path, _, _ in WEBSOCKETS]
    consumers = frontend_consumers([path for _, path, _ in operations] + ws_paths)

    lines = [
        "# 生成的 API 索引（勿手改）",
        "",
        "> 由 apps/api/scripts/extract_api_index.py 从 apps/api/openapi.json + "
        "apps/web/src/App.tsx 生成；",
        "> CI 用 --check 拦截漂移。改动端点或路由后请重新生成并提交。",
        "",
        f"端点总数：{len(operations)}（另有 WebSocket {len(WEBSOCKETS)} 条）",
        "",
        "## 端点（apps/api/openapi.json）",
        "",
        "| 方法 | 路径 | 说明 | 权限 | 幂等语义 | 前端消费点 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for method, path, operation in operations:
        summary = (operation.get("summary") or "").strip()
        description = (operation.get("description") or "").strip().splitlines()
        text = summary or (description[0] if description else "")
        auth = "公开" if path in PUBLIC_PATHS else "需登录"
        body = _body_properties(document, operation)
        lines.append(
            f"| {method.upper()} | {path} | {text} | {auth} | "
            f"{idempotency_for(method, path, body)} | {_cell(consumers[path])} |"
        )

    lines += [
        "",
        "## WebSocket（不进 OpenAPI，单独维护）",
        "",
        "| 协议 | 路径 | 说明 | 权限 | 幂等语义 | 前端消费点 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for path, text, auth in WEBSOCKETS:
        lines.append(
            f"| WS | {path} | {text} | {auth} | 握手票据一次性 | {_cell(consumers[path])} |"
        )

    lines += [
        "",
        "## 前端路由（apps/web/src/App.tsx）",
        "",
        "| 路由 | 页面组件 | 定义处 |",
        "| --- | --- | --- |",
    ]
    for path, label in frontend_routes():
        lines.append(f"| {path} | {label} | \u0060apps/web/src/App.tsx\u0060 |")

    lines += [
        "",
        "## 读法",
        "",
        "- **权限**：需登录 = 会话 cookie；公开 = 见脚本里的 PUBLIC_PATHS；"
        "ticket = WS 一次性票据。",
        "- **幂等语义**：GET/PUT/DELETE 天然幂等；POST 的幂等键由请求体字段推出"
        "（request_id、client_message_id 是入库去重键，同键重放返回既有结果）；",
        "  状态机写操作按 FSM 语义标注（回放或 409，不会重复落库）。",
        "- **前端消费点**：apps/web/src 下引用该路径的源文件（不含测试与生成的 schema.d.ts）；",
        "  — 表示没有路径字面量，可能通过响应里的 url 字段间接使用。",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="generate the API index skill")
    parser.add_argument("--check", action="store_true", help="fail when the file is stale")
    parser.add_argument("--target", type=Path, default=TARGET, help="output file (tests, tools)")
    args = parser.parse_args(argv)

    rendered = render()
    if args.check:
        if not args.target.exists():
            print(f"{args.target} is missing; run the generator", file=sys.stderr)
            return 1
        if args.target.read_text(encoding="utf-8") != rendered:
            print(
                f"{args.target} is stale; run: uv run --project apps/api python "
                "apps/api/scripts/extract_api_index.py",
                file=sys.stderr,
            )
            return 1
        print("API index is up to date")
        return 0

    args.target.parent.mkdir(parents=True, exist_ok=True)
    args.target.write_text(rendered, encoding="utf-8")
    print(f"wrote {args.target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
