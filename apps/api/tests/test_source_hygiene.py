"""Source hygiene: docstrings must not smuggle invalid escape sequences.

A non-raw docstring containing a backslash-backtick (easy to type when writing Markdown
inside code) only warns on a *fresh* compile, so CI catches it while a warm \`.pyc\` cache
hides it locally. This test compiles every source file with warnings as errors, which
turns that whole class of issue into a normal test failure.
"""

from __future__ import annotations

import warnings
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"


def test_sources_compile_without_syntax_warnings() -> None:
    offenders: list[str] = []
    for path in sorted(SOURCE_ROOT.rglob("*.py")):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
        for warning in caught:
            if issubclass(warning.category, SyntaxWarning):
                offenders.append(f"{path.relative_to(SOURCE_ROOT)}: {warning.message}")

    assert offenders == [], "syntax warnings in source files: " + "; ".join(offenders)
