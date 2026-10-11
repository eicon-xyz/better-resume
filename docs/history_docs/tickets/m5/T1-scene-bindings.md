# M5-T1 — 场景与绑定：枚举 + 表 + 迁移 + 默认绑定

- blocking：M4
- 纪律：先写失败测试（红），再实现（绿）；**合并后行为必须与 M4 完全一致**（回归全绿）

## 目标

把"哪个 AI 场景用哪个供应商"从散落在调用点的 model_ref 提升为**一等公民的数据**：
场景枚举（业务语义）+ 绑定行（供应商 + 目标引用），为 T6 的"换供应商不改业务码"打地基。

## 交付物

- `llm_gateway/scenes.py`：`LlmScene` 枚举（**业务语义，不含供应商**）：
  `chat` / `question_extraction` / `answer_evaluation` / `follow_up` / `report_summary`
  —— 每个场景带 docstring 说明"输入什么、要什么形状的输出"
- `llm_gateway/binding_orm.py` + 迁移 `0005_scene_bindings`：
  `llm_scene_bindings(scene PK, adapter, target_ref, updated_at)`，
  `adapter ∈ {"openai_compat", "xingyun"}`，`target_ref` 对前者是 model_ref、对后者是 flow_id
- `llm_gateway/binding_store.py`：`SceneBindingStore`（读全部 / 单场景读 / upsert / 校验），
  校验规则：未知 adapter → 明确错误；target_ref 为空 → 明确错误
- **默认绑定种子**：五个场景全部 `openai_compat` + 现有默认 model_ref（行为与 M4 一致）
- 测试：`tests/llm_gateway/test_scene_bindings.py`（≥8 例）

## 测试

| 用例 | 断言 |
| --- | --- |
| 枚举完备 | 五个场景都有定义；枚举值与前端可读字符串一致 |
| 迁移 | 空库升级到 head 后表存在；再次 upgrade 幂等；`alembic check` 干净 |
| 默认种子 | 五个场景各一行，adapter=openai_compat |
| upsert | 同场景二次写入是更新而不是插入；updated_at 变化 |
| 校验 | 未知 adapter / 空 target_ref → 抛明确错误（不静默） |
| 未知场景 | 读到缺失场景时返回 None 而不是抛错（由 Resolver 决定语义） |

## 验收

| 命令 | 期望 |
| --- | --- |
| `uv run pytest -q tests/llm_gateway/test_scene_bindings.py` | 全绿 |
| `uv run alembic upgrade head && uv run alembic check` | 干净 |
| 全量回归 | `uv run pytest -q` 与 M4 基线一致（473 + 新增） |

## 不做

- 不做按用户/按会话的绑定（Q3）；不做前端编辑（T7）；不做绑定历史/审计表。

