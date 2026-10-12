# T1 — 仓库地基与工具链固定

- blocking：无
- 前置决策：D-A（uv + Python 3.12 安装方式）、D-B（git 提交身份）

## 目标

把「只有 docs/ 的目录」变成 D08 形态的可提交 monorepo 空架子，并固定工具链版本。

## 交付物

- `git init -b main`（**已执行**）；`.gitignore`（Python/Node/env/IDE/docker 数据卷）
- `LICENSE`（MIT，D17）、`.editorconfig`、`.gitattributes`
- `.python-version` = 3.12；`package.json`（engines.node >= 20）；`pnpm-workspace.yaml`（apps/*）
- 目录占位：`apps/api/`、`apps/web/`、`skills/`；`docs/tickets/m0/`（本目录）
- `apps/api/pyproject.toml`（uv 管理）、`apps/api/uv.lock`
- README「当前状态 / 结构」两段更新为实际形态（根目录文件，非 docs/）

## 验收

| 命令 | 期望 |
| --- | --- |
| `uv --version` | 有版本号（uv 已装） |
| `uv run --project apps/api python -V` | Python 3.12.x |
| `node -v` / `pnpm -v` | >= 20 / 有版本号 |
| `git log --oneline` | 至少 1 条提交，message 说 WHAT |
| `git status --short` | 除预期未跟踪文件外干净 |
| `git grep -nE "sk-[A-Za-z0-9]{16,}"` | 无命中（无密钥入库） |

## 形态提议（待确认）

- Python 包名 `better_resume`，源码在 `apps/api/src/better_resume/`（src layout，避免与三方包重名）。
- `skills/` 只建目录 + `.gitkeep`，不含任何知识库内容（对齐 kickoff「skills 不在 M0」与
  完成标准「skills 占位」——见 OPEN-QUESTIONS D-D）。
- apps/api 依赖：fastapi、uvicorn[standard]、pydantic-settings、structlog、sqlalchemy[asyncio]、
  asyncpg、alembic、redis、httpx；dev：pytest、pytest-asyncio、ruff、fakeredis。

## 不做

- 不建 skills 知识库内容、不建 worker/nginx、不写业务逻辑。
