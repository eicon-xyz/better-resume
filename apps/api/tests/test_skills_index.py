"""Skills knowledge base: structure, drift and cross-reference checks (M6-T7).

Same discipline as openapi.json / schema.d.ts: the committed index must equal what the
generator renders, and --check must fail on drift. The module SKILL.md files are the
"invariants and traps" layer, so their structure and their citations are asserted here too.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from functools import cache
from pathlib import Path

import pytest

API_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = API_ROOT.parents[1]
SKILLS = REPO_ROOT / "skills"
MODULES = SKILLS / "modules"
REPO_MAP = SKILLS / "repo-map/SKILL.md"
SKILLS_README = SKILLS / "README.md"
GENERATED_INDEX = SKILLS / "api-index/generated-api-index.md"
GENERATOR = API_ROOT / "scripts/extract_api_index.py"
OPENAPI = API_ROOT / "openapi.json"
APP_TSX = REPO_ROOT / "apps/web/src/App.tsx"
CI_WORKFLOW = REPO_ROOT / ".github/workflows/ci.yml"
TICKETS = REPO_ROOT / "docs/tickets"

MAX_LINES = 80
REQUIRED_SECTIONS = [
    "## 职责",
    "## 对外接口",
    "## 不变量",
    "## 已知陷阱",
    "## 测试地图",
    "## 常见变更配方",
]
ENDPOINT_COLUMNS = ["方法", "路径", "说明", "权限", "幂等语义", "前端消费点"]
#: The ticket names these modules; "migrations" is the directory name of db_and_migrations.
MODULE_DIRS = {
    "settings": "settings",
    "identity": "identity",
    "conversation": "conversation",
    "llm_gateway": "llm_gateway",
    "ai_resilience": "ai_resilience",
    "interview_engine": "interview_engine",
    "resume_parser": "resume_parser",
    "media": "media",
    "http": "http",
    "migrations": "db_and_migrations",
}
#: repo-map has to route all of the above plus the web app (which has no module SKILL.md).
REPO_MAP_TARGETS = sorted({*MODULE_DIRS, "web"})

CITATION = re.compile(r"M(\d)\s*P(\d+)")
BARE_PROBLEM_ID = re.compile(r"(?<![\w])P(\d+)(?![\w])")
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}
CODE_FENCE = "\u0060\u0060\u0060"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def module_skill_files() -> list[Path]:
    return sorted(MODULES.glob("*/SKILL.md"))


def run_generator(*args: str, target: Path | None = None) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(GENERATOR), *args]
    if target is not None:
        command += ["--target", str(target)]
    return subprocess.run(  # noqa: S603 - fixed argv, paths come from the repo
        command, cwd=API_ROOT, capture_output=True, text=True, check=False
    )


def table_rows(text: str, marker: str) -> tuple[list[str], list[list[str]]]:
    """Return the (header, rows) of the first markdown table after marker."""
    body = text.split(marker, maxsplit=1)[1]
    header: list[str] = []
    rows: list[list[str]] = []
    for line in body.splitlines():
        if not line.startswith("|"):
            if header:
                break
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if set("".join(cells)) <= set("-: "):
            continue
        if not header:
            header = cells
        else:
            rows.append(cells)
    assert header, "no table found after " + marker
    return header, rows


def index_endpoints() -> list[list[str]]:
    return table_rows(read(GENERATED_INDEX), "## 端点")[1]


def app_route_paths() -> list[str]:
    return re.findall(r'<Route\s+path="([^"]+)"', read(APP_TSX))


@cache
def problem_ids(milestone: str) -> frozenset[str]:
    text = read(TICKETS / milestone / "PROBLEMS.md")
    return frozenset(re.findall(r"^## (P\d+)", text, flags=re.MULTILINE))


def test_every_module_directory_has_a_skill_file() -> None:
    found = {path.parent.name for path in module_skill_files()}
    directories = {path.name for path in MODULES.iterdir() if path.is_dir()}
    assert directories == found, "every skills/modules/<dir> needs a SKILL.md"
    assert found == set(MODULE_DIRS.values())


@pytest.mark.parametrize("path", module_skill_files(), ids=lambda p: Path(p).parent.name)
def test_skill_structure_and_length(path: Path) -> None:
    text = read(path)
    lines = text.splitlines()
    assert len(lines) <= MAX_LINES, str(path) + " has too many lines: " + str(len(lines))
    positions = []
    for section in REQUIRED_SECTIONS:
        assert section in lines, str(path) + " misses the " + section + " section"
        positions.append(lines.index(section))
    assert positions == sorted(positions), str(path) + " sections are out of order"
    assert CODE_FENCE not in text, str(path) + " copies code; keep it to invariants and traps"


def test_repo_map_routes_every_documented_module() -> None:
    text = read(REPO_MAP)
    for target in REPO_MAP_TARGETS:
        assert target in text, "repo-map does not route " + target
    header, rows = table_rows(text, "| 要改的东西 |")
    assert len(header) == 4, str(header)
    assert len(rows) >= len(REPO_MAP_TARGETS)
    for row in rows:
        assert len(row) == 4, str(row)


def test_index_endpoint_set_matches_openapi() -> None:
    document = json.loads(read(OPENAPI))
    expected = {
        (method.upper(), path)
        for path, operations in document["paths"].items()
        for method in operations
        if method in HTTP_METHODS
    }
    header, rows = table_rows(read(GENERATED_INDEX), "## 端点")
    assert header == ENDPOINT_COLUMNS
    for row in rows:
        assert len(row) == len(ENDPOINT_COLUMNS), str(row)
    assert {(row[0], row[1]) for row in rows} == expected


def test_index_lists_frontend_routes_and_consumers() -> None:
    text = read(GENERATED_INDEX)
    header, rows = table_rows(text, "## 前端路由")
    assert header == ["路由", "页面组件", "定义处"]
    assert {row[0] for row in rows} == set(app_route_paths())
    consumers = {row[1]: row[5] for row in index_endpoints()}
    assert "api/client.ts" in consumers["/api/v1/scenes/{scene}"]
    assert "api/client.ts" in consumers["/api/v1/chat/sessions/{session_id}/stream"]


def test_committed_index_is_not_stale() -> None:
    result = run_generator("--check")
    assert result.returncode == 0, result.stdout + result.stderr


def test_check_fails_on_drift_and_regeneration_repairs_it(tmp_path: Path) -> None:
    target = tmp_path / "generated-api-index.md"
    target.write_text("# 生成的 API 索引（勿手改）\n\n端点总数：0\n", encoding="utf-8")
    drift = run_generator("--check", target=target)
    assert drift.returncode != 0
    assert "stale" in drift.stdout + drift.stderr

    assert run_generator(target=target).returncode == 0
    assert run_generator("--check", target=target).returncode == 0
    assert read(target) == read(GENERATED_INDEX)


def test_ci_runs_the_index_drift_check() -> None:
    assert "extract_api_index.py --check" in read(CI_WORKFLOW)


def test_skills_readme_explains_both_audiences_and_the_real_path() -> None:
    text = read(SKILLS_README)
    assert "apps/api/scripts/extract_api_index.py" in text
    assert "--check" in text
    assert "给人" in text and "agent" in text


@pytest.mark.parametrize(
    "path", [REPO_MAP, *module_skill_files()], ids=lambda p: Path(p).parent.name
)
def test_problem_citations_resolve(path: Path) -> None:
    for number, line in enumerate(read(path).splitlines(), start=1):
        for match in CITATION.finditer(line):
            milestone, problem = "m" + match.group(1), "P" + match.group(2)
            assert problem in problem_ids(milestone), (
                str(path) + ":" + str(number) + " cites " + milestone + " " + problem
            )
        rest = CITATION.sub("", line)
        bare = BARE_PROBLEM_ID.search(rest)
        assert bare is None, (
            str(path) + ":" + str(number) + " cites a problem id without its milestone"
        )


@pytest.mark.parametrize("path", module_skill_files(), ids=lambda p: Path(p).parent.name)
def test_every_module_skill_cites_problem_history(path: Path) -> None:
    assert CITATION.search(read(path)), str(path) + " cites no docs/tickets/m*/PROBLEMS.md entry"
