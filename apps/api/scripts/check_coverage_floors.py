"""P2-T6 round 2: per-module coverage floors for the deep modules.

Criterion (user decision, codebase-design vocabulary): a module gets a floor when it passes
the deletion test, has a small stable interface, and hides thick implementation. Shallow
modules (adapters/factories/route shells) deliberately get NO floor -- they are verified by
seam contracts instead. Reads the coverage JSON written by the unit layer and refuses
(exit 2) listing every deep module below its floor."""

from __future__ import annotations

import argparse
import json
import sys

#: module -> floor (percent of statements covered).
#: Rationale: docs/tickets/p2-test-automation/README.md §5.5.
DEEP_MODULES: dict[str, float] = {
    "ai_resilience": 90.0,
    "identity": 90.0,
    "interview_engine": 90.0,
    "jobs": 90.0,
    "llm_gateway": 90.0,
    "media": 90.0,
    "resume_parser": 90.0,
}


def module_percents(data: dict) -> dict[str, float]:
    per_file = data.get("files", {})
    mods: dict[str, list[int]] = {}
    for path, payload in per_file.items():
        if "/better_resume/" not in path:
            continue
        mod = path.split("better_resume/")[1].split("/")[0]
        summary = payload.get("summary", {})
        covered, total = mods.get(mod, [0, 0])
        mods[mod] = [
            covered + int(summary.get("covered_lines", 0)),
            total + int(summary.get("num_statements", 0)),
        ]
    return {
        mod: round(100 * covered / total, 1)
        for mod, (covered, total) in sorted(mods.items())
        if total > 0
    }


def check(data: dict) -> tuple[int, list[str]]:
    percents = module_percents(data)
    violations: list[str] = []
    for mod, floor in DEEP_MODULES.items():
        if mod not in percents:
            violations.append(f"{mod}: no coverage data (floor {floor}%)")
        elif percents[mod] < floor:
            violations.append(f"{mod}: {percents[mod]}% < floor {floor}%")
    return (2 if violations else 0), violations


def main() -> int:
    parser = argparse.ArgumentParser(description="enforce deep-module coverage floors")
    parser.add_argument("--json", default="var/evidence/coverage-api.json")
    args = parser.parse_args()
    try:
        data = json.loads(pathlib.Path(args.json).read_text(encoding="utf-8"))
    except FileNotFoundError:
        print("coverage JSON missing; run verify.sh --layer unit first", file=sys.stderr)
        return 2
    percents = module_percents(data)
    print("deep-module coverage:")
    for mod in sorted(percents):
        floor = DEEP_MODULES.get(mod)
        marker = f" (floor {floor}%)" if floor else ""
        print(f"  {mod}: {percents[mod]}%{marker}")
    code, violations = check(data)
    for violation in violations:
        print(f"FLOOR VIOLATION: {violation}", file=sys.stderr)
    if violations:
        return 2
    print("floors ok")
    return 0


import pathlib  # noqa: E402  (used by main; kept late to keep the floors table on top)

if __name__ == "__main__":
    raise SystemExit(main())
