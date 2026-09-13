# better-resume-api

FastAPI 单体（M0 骨架）。本地命令：

```bash
uv sync
uv run ruff check . && uv run ruff format --check .
uv run pytest
uv run uvicorn better_resume.main:app --port 8000
```

> 本机（WSL 沙箱）备注：uv 缓存目录需指向工作区内，例如
> `UV_CACHE_DIR="$(git rev-parse --show-toplevel)/.cache/uv"`；CI 与常规开发机不需要。
