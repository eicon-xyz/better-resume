# M6-T9 — M6 验收证据 + PROBLEMS 收口 + 简历草稿 + PR

- blocking：M6-T1..T8
- 纪律：证据可复跑；偏差如实写

## 交付物

- `docs/tickets/m6/ACCEPTANCE.md`：
  1. §12.4 验收对照：kill 实例 drill 的完整输出（含实例 id 与 kill→恢复耗时）
  2. 分布式单飞/锁的机制证据（两实例并发同 key 上游只调一次；锁互斥与接管用例）
  3. 容量报告摘要（`docs/perf/M6-capacity.md` 的关键数字 + 环境说明）
  4. skills 知识库清单与漂移检查结果
  5. 本地 CI 全矩阵（12 条 + 新增的索引检查、drill 说明）
  6. **未验证项**（真模型高并发、生产网络、多可用区、真机凭据相关项）
  7. 与提案的偏差清单
- `docs/tickets/m6/PROBLEMS.md`：实现中的难题与解决办法（预计：锁续租的时钟、单飞 fencing 的竞态、
  Redis Stream 的 pending 重投、compose 健康检查窗口、nginx SSE 缓冲、压测数字的误读风险等）
- `docs/resume/M6-resume-draft.md`（D14）：分布式与容量数字
- `README.md`：M6 状态、部署章节（compose 形态/扩缩容/kill drill）、skills 用法
- PR：gh 建 PR → 双 job 绿 → 合并 → main 复跑绿

## 验收

| 命令 | 期望 |
| --- | --- |
| `uv run pytest -q` | 全绿（M5 528 → M6 目标 ≥ 600） |
| `pnpm -C apps/web test --run` | 全绿（158 → ≥ 165，若有前端改动） |
| `docker compose up -d --wait` | 五服务 healthy；drill 通过 |
| `gh pr checks` | 双 job success |

## 不做

- 不做 M7 内容（不存在）；不顺手重构无关模块；不把压测数字包装成营销结论。

