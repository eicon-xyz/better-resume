"""Export the FastAPI OpenAPI document; --check fails when the committed file is stale.

The backend is the single source of truth for the wire contract (D17): the frontend type
file is generated from apps/api/openapi.json, and CI refuses to merge drift.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from better_resume.main import create_app

OUTPUT = Path(__file__).resolve().parents[1] / "openapi.json"


def render() -> str:
    """Stable rendering: sorted keys + fixed indent, so diffs are meaningful."""
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
