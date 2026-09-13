# T8 — CI 双 job + 本地等价命令验证

- blocking：T2 T3 T5 T6 T7

## 目标

D17 的 GitHub Actions 双 job 文件就位且语法校验通过；本地用同样命令逐条跑绿
（GitHub remote 建好后可直接开 PR）。

## 交付物

- `.github/workflows/ci.yml`
  - **backend**：`ubuntu-latest` + service containers（postgres:16 / redis:7）+
    `astral-sh/setup-uv` + `uv sync --frozen` -> `ruff check` -> `ruff format --check` ->
    `pytest` -> `alembic check`
  - **frontend**：`pnpm/action-setup` + `actions/setup-node`（cache: pnpm）+
    `pnpm install --frozen-lockfile` -> `lint` -> `typecheck` -> `vitest run`
- 校验命令与结果固化在 `docs/tickets/m0/ACCEPTANCE.md`（T9 产出）

## 验收

| 命令 | 期望 |
| --- | --- |
| `python3 -c "import yaml;yaml.safe_load(open('.github/workflows/ci.yml'))"` | exit 0（YAML 语法） |
| `uvx check-jsonschema --builtin-schema vendor.github-workflows .github/workflows/ci.yml` | exit 0（结构校验；不可用时退化为 actionlint，方案在 OPEN-QUESTIONS D-G 定） |
| 本地逐条执行 workflow 中每个 run 命令 | 全部 exit 0，输出摘要进 T9 证据 |

## 形态提议（待确认）

- CI Node 版本：提议 **22**（与本机 v22.23.2 一致，命令等价）；若你要求 20 我改成 20。
- 不引 matrix、不引部署 job、不加 PR 模板（范围外）。

## 不做

- 不做 CD、不做镜像发布、不接 codecov。
