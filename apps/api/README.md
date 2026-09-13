# better-resume-api

FastAPI 单体。本地命令：

```bash
uv sync
uv run ruff check . && uv run ruff format --check .
uv run pytest
uv run uvicorn better_resume.main:app --port 8000
```

## 本地数据库

三种环境，靠 `BR_DATABASE_URL` 区分，代码里没有任何硬编码：

| 环境 | Postgres 位置 | 说明 |
| --- | --- | --- |
| CI | `localhost:5432`（service container） | workflow 里注入 |
| compose | `postgres:5432`（容器网络内） | compose.yaml 注入 |
| 本机 WSL（无 Docker 时） | `127.0.0.1:5433`（原生 postgresql-14） | 见下 |

```bash
# 本机原生库（Docker Desktop 不可用时）
export BR_DATABASE_URL="postgresql+asyncpg://better_resume:better_resume@127.0.0.1:5433/better_resume"
uv run alembic upgrade head && uv run pytest
```

> 本机（WSL 沙箱）备注：uv 缓存目录需指向工作区内，例如
> `UV_CACHE_DIR="$(git rev-parse --show-toplevel)/.cache/uv"`；CI 与常规开发机不需要。
