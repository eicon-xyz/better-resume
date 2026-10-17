#!/usr/bin/env python3
"""对未被应用测试覆盖的每个脚本做语法扫描。

存在理由（retro 2026-10-06）：`scripts/*.sh` 与仓库级 `scripts/*.py` 此前没有任何护栏——
`verify.sh` 会跑演练脚本的 pytest，却从不看同目录下的 shell 脚本，于是一个永远退出 0 的
证明脚本能穿过绿色 CI。这里还把 SyntaxWarning 提升为错误：docstring 里的非法转义序列是
潜在缺陷，而 `apps/api/tests/test_source_hygiene.py` 只守应用包。

用法：uv run --project apps/api python scripts/check_scripts.py
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
