#!/usr/bin/env python3
"""分两级检查 docs/audit/units/*.json 里的审计数据。

用法：
  python3 scripts/verify_audit_evidence.py [--structural] [--strict] [--json OUT] [--units DIR] [unit ...]

级别：
  （始终）      结构级：每条问题都有必需字段，每个 "where" 引证都能解析、且指向该文件里真实
                存在的行区间。对代码漂移稳定，是 CI 跑的级别。
  （默认）      佐证报告：每个被引窗口是否仍包含问题证据里引用的一行？探索性——无法验证的
                声明判失败，部分佐证的声明不判失败。
  （--strict）  佐证闸门：部分佐证的声明也判失败。代码一动行号就变，所以它属于审计/修复收口，
                不属于 CI。

为什么拆两级（D22）：只挪了行的重构不能让 CI 变红，但审计数据仍要在稳定的级别上被查腐。你
动过 docs/audit/ 或它引用的文件时，手动跑 --strict。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UNITS = ROOT / "docs" / "audit" / "units"
WHERE_RE = re.compile(r"^(?P<path>[^\s:]+):(?P<start>\d+)(?:-(?P<end>\d+))?$")
#: "12" | "12-18" | "12-18,30-31"——units/*.json 里实际用到的形态。
LINE_SPEC_RE = re.compile(r"^\d+(?:-\d+)?(?:,\d+(?:-\d+)?)*$")
#: 每条问题都必须携带的字段，与审计主题无关。
STRUCTURAL_FIELDS = ("id", "dim", "severity", "title", "where", "why", "fix")

# 证据块有三种标注形态；剥掉标注，保留代码：
#   "123: code"、"123  code"、"123|  code"、"path/to/file.py:123  code"。
EVIDENCE_PREFIX = re.compile(
    r"^\s*(?:[\w./()\u4e00-\u9fff -]+?\.(?:py|ts|tsx|md|yaml|yml|json|sh|sql))?(?::)?\d+\s*[:|]?\s+"
)


def norm(text: str) -> str:
    return re.sub(r"\s+", "", text)


def file_lines(rel: str) -> list[str] | None:
    path = ROOT / rel
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8", errors="replace").splitlines()


def citation_spans(where: str) -> list[tuple[str, int, int]] | None:
    """`path:12-18,30` -> [(path, 12, 18), (path, 30, 30)]；无法解析时为 None。"""
    if ":" not in where:
        return None
    rel, spec = where.rsplit(":", 1)
    spec = spec.strip()
    if not rel or not LINE_SPEC_RE.match(spec):
        return None
    spans: list[tuple[str, int, int]] = []
    for part in spec.split(","):
        if "-" in part:
            start_text, _, end_text = part.partition("-")
            start, end = int(start_text), int(end_text)
        else:
            start = end = int(part)
        spans.append((rel.strip(), start, end))
    return spans


def check_structure(data: dict, unit_name: str) -> tuple[list[str], int, int]:
    """仅结构级检查：字段齐全、引证可解析、被引行区间存在。

    返回 (problems, issue_count, citation_count)。
    """
    problems: list[str] = []
    issues = data.get("issues")
    if not isinstance(issues, list) or not issues:
        return [f"{unit_name}: no issues[] list"], 0, 0
    citations = 0
    for issue in issues:
        if not isinstance(issue, dict):
            problems.append(f"{unit_name}: an issue is not an object")
            continue
        iid = str(issue.get("id") or "<no id>")
        for field in STRUCTURAL_FIELDS:
            if not issue.get(field):
                problems.append(f"{unit_name}/{iid}: missing {field}")
        for where in issue.get("where") or []:
            spans = citation_spans(str(where))
            if spans is None:
                problems.append(f"{unit_name}/{iid}: unparseable where {where!r}")
                continue
            citations += len(spans)
            for rel, start, end in spans:
                lines = file_lines(rel)
                if lines is None:
                    problems.append(f"{unit_name}/{iid}: missing file {rel}")
                    continue
                if start < 1 or end < start or end > len(lines):
                    problems.append(
                        f"{unit_name}/{iid}: {rel}:{start}-{end} outside 1..{len(lines)}"
                    )
    return problems, len(issues), citations


def check_issue(issue: dict) -> tuple[str, list[str]]:
    """返回 (status, details)。status 取 ok|partial|fail|skip。

    每条引证至少要被一行证据佐证；全部引证都被佐证时整条问题为 "ok"，部分被佐证为
    "partial"，无一被佐证为 "fail"。
    """
    evidence_lines = [
        EVIDENCE_PREFIX.sub("", line).strip() for line in (issue.get("evidence") or "").split("\n")
    ]
    evidence_lines = [line for line in evidence_lines if line]
    cited = []
    for where in issue.get("where", []):
        match = WHERE_RE.match(where.strip())
        if match:
            cited.append(
                (
                    match.group("path"),
                    int(match.group("start")),
                    int(match.group("end") or match.group("start")),
                )
            )
    if not cited:
        return "skip", ["no plain file:line in where (comma lists are checked structurally)"]
    if not evidence_lines:
        return "skip", ["no evidence text"]

    corroborated = 0
    details: list[str] = []
    for rel, start, end in cited:
        lines = file_lines(rel)
        if lines is None:
            details.append(f"MISSING FILE {rel}")
            continue
        window = norm("".join(lines[max(0, start - 1):end]))
        hits = sum(1 for line in evidence_lines if norm(line) in window)
        if hits:
            corroborated += 1
        details.append(f"{rel}:{start}-{end}: {hits}/{len(evidence_lines)} evidence lines in window")
    if corroborated == 0:
        return "fail", details
    if corroborated < len(cited):
        return "partial", details
    return "ok", details


def main(argv: list[str] | None = None) -> int:
    """CLI：[--structural] [--strict] [--json OUT] [--units DIR] [unit ...]。"""
    args = list(sys.argv[1:] if argv is None else argv)
    strict = "--strict" in args
    structural = "--structural" in args
    args = [arg for arg in args if arg not in ("--strict", "--structural")]
    json_out: str | None = None
    if "--json" in args:
        index = args.index("--json")
        json_out = args[index + 1] if index + 1 < len(args) else ""
        del args[index : index + 2]
        if not json_out:
            print("--json needs an output path", file=sys.stderr)
            return 2
    units_dir = UNITS
    if "--units" in args:
        index = args.index("--units")
        raw = args[index + 1] if index + 1 < len(args) else ""
        del args[index : index + 2]
        if not raw:
            print("--units needs a directory", file=sys.stderr)
            return 2
        units_dir = Path(raw)
        if not units_dir.is_dir():
            print(f"--units is not a directory: {units_dir}", file=sys.stderr)
            return 2
    wanted = set(args)

    problems: list[str] = []
    records: list[dict[str, object]] = []
    failures = partial = ok = 0
    units_checked = issues_seen = citations_seen = 0
    for path in sorted(units_dir.glob("*.json")):
        if path.stem == "EXAMPLE":
            continue
        if wanted and path.stem not in wanted:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"cannot parse {path.name}: {exc}", file=sys.stderr)
            return 2
        if not isinstance(data, dict):
            continue  # 不是审计单元文件（临时 JSON 可能同目录）
        units_checked += 1
        unit_problems, issue_count, citation_count = check_structure(data, path.stem)
        problems.extend(unit_problems)
        issues_seen += issue_count
        citations_seen += citation_count
        if structural:
            continue
        for issue in data.get("issues", []):
            status, details = check_issue(issue)
            records.append({"unit": path.stem, "id": issue.get("id"), "status": status})
            if status in ("ok", "skip"):
                ok += 1
                continue
            mark = "FAIL " if status == "fail" else "PART "
            if status == "fail":
                failures += 1
            else:
                partial += 1
            print(f"{mark} [{path.stem}] {issue.get('id')}: {issue.get('title', '')[:70]}")
            for detail in details:
                print(f"        {detail}")

    if problems:
        for problem in problems:
            print(f"STRUCT {problem}")
        print(f"\n{len(problems)} structural problem(s) in {units_checked} unit(s)")
        return 1

    if structural:
        print(
            f"structure ok: {units_checked} units / {issues_seen} issues / {citations_seen} citations"
        )
        return 0

    if json_out:
        Path(json_out).write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n")
        print(f"wrote {json_out}")

    print(f"\nverifiable: {ok}  partial: {partial}  unverifiable: {failures}")
    if failures:
        return 1
    if strict and partial:
        print(
            f"STRICT: {partial} claim(s) cite a place their own evidence block does not",
            " corroborate (usually line drift). Re-anchor the citation or refresh the evidence.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
