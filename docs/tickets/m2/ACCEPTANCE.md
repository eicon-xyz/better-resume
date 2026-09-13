# M2 验收证据（面试里程碑）

> 执行日期：2026-09-13 · 分支 `m2/interview-engine` · 依据 docs/tickets/m2/（T1–T10）
> §12.4 的 M2 验收：**上传简历 → 完整面试 → 雷达图报告**

## 1. 真实端到端记录（真实模型，非夹具）

`apps/api/scripts/interview_smoke.py`（真实调用 DeepSeek，走完整 HTTP 链路）：

```
login: 200
session: f6ae94bb-1ffd-4389-ac62-bafb56a2c418 draft
questions: 3  resume_score=82.0
  1. 你提到用 Python 重写批量写入后 P99 从 800ms 降到 120ms。请先讲一下：重写之前这条链路的写入是怎…
  2. 你设计了幂等键与补偿任务，把线上重复写入从每天 200 条降到 0。请说明幂等键是怎么构造和存储的…
  3. 把这几个改动放在一起看：批量写入提升了吞吐、幂等键消灭了重复写入，但两者是有代价的…
answered 1:     score=50.0 next=follow_up  next_no=1-F1 reason=AI_SUGGESTED
answered 1-F1:  score=42.0 next=follow_up  next_no=1-F2 reason=AI_SUGGESTED
answered 1-F2:  score=18.0 next=next_question next_no=2  reason=FOLLOW_UP_LIMIT_REACHED
answered 2:     score=22.0 next=follow_up  next_no=2-F1 reason=AI_SUGGESTED
answered 2-F1:  score=22.0 next=follow_up  next_no=2-F2 reason=AI_SUGGESTED
answered 2-F2:  score=18.0 next=next_question next_no=3  reason=FOLLOW_UP_LIMIT_REACHED
report: {
  "overall": 28.7,
  "dimensions": {"accuracy": 36.0, "depth": 25.0, "coverage": 16.0, "completeness": 66.7},
  "turns": 7,
  "follow_ups": 4,
  "suggestions": ["反复缺失的要点：…", "回答偏结论、缺过程：补充当时的取舍、失败尝试与量化结果",
                  "有题目未作答，建议完整走完一轮面试再评估"],
  "summary": "本次模拟面试综合得分 28.7，其中完成度 66.7 相对最高…"
}
finish idempotent: True
```

这段记录同时证明了 §12.4 的三件事与四条关键不变量：

| 观察到的行为 | 对应设计 |
| --- | --- |
| 题目内容引用了简历里的 P99、幂等键、重复写入数字 | **反幻觉**：出题只用解析出的 ResumeContext（D10） |
| 每题得分偏低时自动追问，且题号为 `1-F1` / `1-F2` | 追问裁决链（§4.1.3）+ 题号值对象 |
| `1-F2` 之后回到主问题 `2`，reason=`FOLLOW_UP_LIMIT_REACHED` | 追问上限 `maxFollowUp=2` + 计数按主题重置 |
| 同一会话 finish 两次得到同一份报告 | 报告冻结快照 + 幂等收口 |
| 报告四维与逐题回放（7 条，含 4 条追问） | 报告聚合（纯函数，LLM 只写总结句） |

> 真实演示的另一个用途：暴露了「模型写的缺失要点是整句」导致建议行过长的问题 →
> 已加 `shorten_point()`（32 字截断 + 空白折叠）并有单测，见 `test_report_suggestions.py`。

## 2. 本地 CI 矩阵（12 条命令全部 exit=0）

| # | 命令 | 结果 |
| --- | --- | --- |
| 1 | `uv sync --frozen` | exit=0 |
| 2 | `uv run ruff check .` | All checks passed |
| 3 | `uv run ruff format --check .` | exit=0 |
| 4 | `uv run pytest` | **324 passed**（M1: 94 → M2: 324） |
| 5 | `uv run alembic upgrade head` | 至 `c28d77ba4f32` |
| 6 | `uv run alembic check` | No new upgrade operations detected |
| 7 | `uv run python scripts/export_openapi.py --check` | up to date |
| 8 | `pnpm install --frozen-lockfile` | exit=0 |
| 9 | `pnpm -C apps/web lint` | exit=0（0 error / 0 warning） |
| 10 | `pnpm -C apps/web typecheck` | exit=0 |
| 11 | `pnpm -C apps/web test` | **104 passed**（M1: 65 → M2: 104） |
| 12 | `pnpm -C apps/web check:api` | 生成物无 diff |

> 本机环境说明：Docker 不可用后，本地用**原生 PostgreSQL 14（5433）+ 原生 Redis 6（6379）**跑；
> CI 仍是 service container 的 5432 + 6379，命令完全一致（见 `apps/api/README.md`）。

## 3. 票据完成情况

| 票 | 内容 | 证据 |
| --- | --- | --- |
| T1 | resume-parser 混合解析（无 LLM） | 18 个用例（中英 PDF、CJK 回退、扫描件降级） |
| T2 | 领域模型 + 两层状态机 | 迁移 `c28d77ba4f32`；36+25 例转移表穷举、10 并发 CAS |
| T3 | 出题链路 | 19 例（schema 失败不留半截状态、重复调用回放、并发 409） |
| T4 | 答题/评分链路 | 幂等回放、10 并发同题只评一次、失败回滚可重答 |
| T5 | 追问裁决 + 生成 | 72 例判定表穷举、fail-open、F1→F2→回主问题 |
| T6 | 恢复/结束/报告 | 派生回写、finish 幂等、报告快照、总结失败不影响数字 |
| T7 | 前端上传页 | 魔数校验、上传进度、解析预览、「继续上次」 |
| T8 | 面试房间 | 防重复提交、追问徽章、恢复、结束握手 |
| T9 | 报告页 | 自绘 SVG 雷达（几何纯函数 11 例）、逐题回放、空态 |
| T10 | 本文件 | — |

## 4. 与提案的偏差（诚实记录）

1. **雷达四维命名**：Q3 原提议「准确性/深度/表达/结构性」→ 实际为
   **准确性/深度/要点覆盖/完成度**（只有分数与缺失要点两类信号，凑表达/结构性会成为假指标）。
2. `Stage` 增加 `CHAT`（M1 已记）；M2 新增无。
3. 追问生成走 `Stage.FOLLOWUP`、报告总结走 `Stage.EVALUATION`（`§12.2` 的 stage 集合未含"报告"）。
4. 建议行对模型写的长缺失要点做 32 字截断（真实演示后新增）。
5. 本地新增原生 Postgres/Redis（Docker 不可用），CI 配置未变。

## 5. 发布流程证据（gh CLI，2026-09-13）

| 步骤 | 结果 |
| --- | --- |
| PR | [#2](https://github.com/eicon-xyz/better-resume/pull/2) `M2: interview milestone …`（`gh pr create`，由我创建） |
| PR CI | run [34756266934](https://github.com/eicon-xyz/better-resume/actions/runs/34756266934)：**backend pass 53s / frontend pass 41s** |
| 合并 | `gh pr merge 2 --merge` → merge commit `6f94684` |
| main CI | run [34756320012](https://github.com/eicon-xyz/better-resume/actions/runs/34756320012)：**success**（backend 15 步 / frontend 13 步，failed=none） |

## 6. 剩余人工事项

1. ~~合并 PR~~ ✅ 已完成（本文件提交时 main 已是 M2 完成态）。
2. **轮换 DeepSeek API key**（曾出现在聊天记录里；`.env` 已被 gitignore，仓库内零命中）。
