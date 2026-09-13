# skills —— 仓库自描述层（D13 / M6-T7）

给人和 agent 同一个入口：**先读这里，再动手**。

## 给人：怎么用

1. 先看 `repo-map/SKILL.md` 的"要改 X → 先看哪"，找到模块、不变量与测试文件；
2. 再读 `modules/<module>/SKILL.md` 的**不变量**与**已知陷阱**——陷阱都带
   `docs/tickets/m*/PROBLEMS.md` 编号（如 M6 P2），能回溯到当时的症状与修法；
3. 要端点清单时看 `api-index/generated-api-index.md`：方法 / 路径 / 权限 / 幂等语义 / 前端消费点 / 前端路由；
4. 验收方式：随便挑 3 个"要改 X"的问题，按上面顺序走，能在 **2 跳**内找到入口（T7 票据要求）。

## 给 agent：怎么用

- **动手前**：`repo-map` 定位 → 对应 `SKILL.md` 读不变量 → 跑"测试地图"里的文件确认基线；
- **改完**：跑该模块的测试；改了端点或前端路由，先重新生成索引再跑 `--check`；
- **写陷阱**：踩到新坑就补进对应模块的"已知陷阱"，引用 PROBLEMS 编号；不复制代码，只写
  "不许违反什么 / 踩过什么坑"，并指向文件与测试。

## 生成物与路径差异（重要）

- 票据里写的 `scripts/extract_api_index.py`，在本仓库对应
  **`apps/api/scripts/extract_api_index.py`**（与 `export_openapi.py` 同一层，用 api 的 uv 环境运行）：

`bash
uv run --project apps/api python apps/api/scripts/extract_api_index.py          # 重新生成
uv run --project apps/api python apps/api/scripts/extract_api_index.py --check  # 漂移检查（非 0 = 漂移）
`

- 生成物永不手改；CI 的 backend job 里有一级 `--check`，与 `openapi.json` / `schema.d.ts` 同级纪律。
- `api-index/generated-api-index.md` 的"前端消费点"由脚本扫描 `apps/web/src` 得出（不含测试与生成的
  `schema.d.ts`）；标 `—` 表示没有路径字面量，可能通过响应里的 url 字段间接使用。
