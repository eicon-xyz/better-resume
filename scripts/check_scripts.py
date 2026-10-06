#!/usr/bin/env python3
"""Syntax sweep for every script that is not covered by the app test suite.

Why this exists (retro 2026-10-06): `scripts/*.sh` and the repo-level `scripts/*.py` had no
guardrail at all - `verify.sh` ran the drill scripts' pytest but never looked at the shell
scripts beside them, so a proof script that always exited 0 shipped through a green CI.
It also promotes SyntaxWarning to an error: an invalid escape sequence in a docstring is a
latent bug, and `apps/api/tests/test_source_hygiene.py` only guards the app package.

Usage: uv run --project apps/api python scripts/check_scripts.py
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCOPE = (ROOT / "scripts", ROOT / "apps" / "api" / "scripts")


def main() -> int:
    checked = 0
    problems: list[str] = []
    for directory in SCOPE:
        for path in sorted(directory.glob("*.py")):
            checked += 1
            source = path.read_text(encoding="utf-8")
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always", SyntaxWarning)
                try:
                    compile(source, str(path), "exec")
                except SyntaxError as exc:
                    problems.append(f"{path.relative_to(ROOT)}: {exc}")
                    continue
            for warning in caught:
                problems.append(f"{path.relative_to(ROOT)}:{warning.lineno}: {warning.message}")

    for problem in problems:
        print(f"FAIL {problem}")
    if problems:
        print(f"\n{len(problems)} problem(s) in {checked} script(s)")
        return 1
    print(f"script syntax ok ({checked} python scripts, SyntaxWarning treated as an error)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
