"""导出 FastAPI OpenAPI 文档；已提交文件过期时 --check 失败。

后端是线上契约的唯一真相源（D17）：前端类型文件由 apps/api/openapi.json 生成，CI 拒绝合并
漂移。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from better_resume.main import create_app

OUTPUT = Path(__file__).resolve().parents[1] / "openapi.json"


def render() -> str:
    """稳定渲染：键排序 + 固定缩进，让 diff 有意义。"""
    schema = create_app().openapi()
    return json.dumps(schema, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    rendered = render()

    if "--check" in args:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if current != rendered:
            print(f"{OUTPUT.name} is stale: run uv run python scripts/export_openapi.py")
            return 1
        print(f"{OUTPUT.name} is up to date")
        return 0

    OUTPUT.write_text(rendered, encoding="utf-8")
    print(f"wrote {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
