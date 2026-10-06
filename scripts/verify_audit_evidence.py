#!/usr/bin/env python3
"""Verify that every audit issue's cited file:line actually contains its evidence.

Usage: python3 scripts/verify_audit_evidence.py [--strict] [--json OUT] [unit ...]

Exploratory mode (default): exit 1 only when a claim is unverifiable.
Gate mode (--strict): exit 1 also when any claim is only partially corroborated -
a citation you cannot check is not evidence.

"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UNITS = ROOT / "docs" / "audit" / "units"
WHERE_RE = re.compile(r"^(?P<path>[^\s:]+):(?P<start>\d+)(?:-(?P<end>\d+))?$")

# Evidence blocks are annotated in three shapes; strip the annotation, keep the code:
#   "123: code", "123  code", "123|  code", "path/to/file.py:123  code".
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


def check_issue(issue: dict) -> tuple[str, list[str]]:
    """Return (status, details). status in ok|partial|fail|skip.

    Each citation must be corroborated by at least one evidence line; the whole issue is
    "ok" when every citation is corroborated, "partial" when some are, "fail" when none is.
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
        return "skip", ["no file:line in where"]
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
    """CLI: [--strict] [--json OUT] [unit ...].

    Default is exploratory: only unverifiable claims fail. --strict is the gate mode:
    a claim whose citations are not all corroborated by its evidence block ("partial")
    fails too, because a citation you cannot check is not evidence.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    strict = "--strict" in args
    args = [arg for arg in args if arg != "--strict"]
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

    failures = partial = ok = 0
    records: list[dict[str, object]] = []
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
            continue  # not an audit unit file (a scratch JSON can sit in the same dir)
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

    if json_out:
        Path(json_out).write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n")
        print(f"wrote {json_out}")

    print(f"\nverifiable: {ok}  partial: {partial}  unverifiable: {failures}")
    if failures:
        return 1
    if strict and partial:
        print(
            f"STRICT: {partial} claim(s) cite a place their own evidence block does not",
            " corroborate. Tighten the evidence or fix the citation.",
            file=sys.stderr,
        )
        return 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
