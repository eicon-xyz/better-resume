# M5-T9 — M5 验收证据 + PROBLEMS 收口 + 简历草稿 + PR

- blocking：M5-T1..T8（T10 可并行，缺凭据则标注未验证）
- 纪律：证据是可复跑的命令输出，不是叙述

## 交付物

- `docs/tickets/m5/ACCEPTANCE.md`：
  1. §12.4 验收对照：**场景绑定切换供应商不改业务码**（附 `git diff --name-only` 证明服务层零改动）
  2. 双 adapter 契约测试矩阵（同一套 10 条 × 2 实现）
  3. 对照表（`adapter_smoke.py` 输出，两个 provider）
  4. 本地 CI 全矩阵（12 条命令逐条 exit=0）
  5. **未验证项**（星云真机 / 云端工作流提示词行为差异）
  6. 与提案的偏差清单
- `docs/tickets/m5/PROBLEMS.md`：实现中的难题与解决办法（预计：SSE 形状不确定、星云错误码语义、
  绑定缓存与并发、别名诱惑、迁移与默认值、前端契约再生等）
- `docs/resume/M5-resume-draft.md`（D14）：双 adapter 接缝 + 场景绑定注册中心的可讲数字
- `README.md`：M5 状态、场景绑定说明、`/settings/ai` 入口、环境变量
- PR：gh 建 PR → 双 job 绿 → 合并 → main 复跑绿

## 验收

| 命令 | 期望 |
| --- | --- |
| `uv run pytest -q` | 全绿（M4 473 → M5 目标 ≥ 520） |
| `pnpm -C apps/web test --run` 等前端四件 | 全绿（152 → ≥ 170） |
| `uv run alembic check` | 干净（新增一张 scene_bindings 表） |
| `gh pr checks` | 双 job success |

## 不做

- 不做 M6 的分布式与压测；不在本票顺手重构无关模块。

