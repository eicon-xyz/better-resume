# M1-T4 — OpenAPI → TS 类型生成 + CI 漂移检查

- blocking：M1-T3

## 目标

D17 的「根治前端猜字段」：后端是唯一 Schema 源，前端类型由 openapi.json 生成，
CI 校验生成物与提交物一致。

## 交付物

- `apps/api/scripts/export_openapi.py`：`create_app()` -> `app.openapi()` ->
  写 `apps/api/openapi.json`（排序稳定、缩进固定，便于 diff）
- `apps/web` 侧：`openapi-typescript` 生成 `src/api/schema.d.ts`；
  `pnpm -C apps/web gen:api`（一条命令跑通导出 + 生成）
- CI 两处新增：
  - backend job 末尾：`uv run python scripts/export_openapi.py --check`（openapi.json 是否需重新生成）
  - frontend job 末尾：`pnpm -C apps/web gen:api --check`（schema.d.ts 是否过期）
- 文档：README 增「契约变更流程」三行（改后端 -> 跑 gen:api -> 提交两处生成物）

## 验收

| 命令 | 期望 |
| --- | --- |
| `cd apps/api && uv run python scripts/export_openapi.py` | 生成/更新 `openapi.json`，二次运行无 diff |
| `pnpm -C apps/web gen:api` | 生成 `src/api/schema.d.ts`，二次运行无 diff |
| 故意改一个 Pydantic 字段后跑 `--check` | 非 0 退出并提示重新生成 |
| `uv run pytest` / `pnpm -C apps/web test` | 不受影响，仍全绿 |

## 形态提议（待确认）

- 生成物**入库**（openapi.json + schema.d.ts），CI 只做漂移检查——评审时能看到契约 diff（Q9 相关）。
- 前端只在类型层消费 schema，运行时不引 openapi 相关依赖。

## 不做

- 不做多版本 API 兼容层；不做客户端 SDK 代码生成（只生成类型）。
