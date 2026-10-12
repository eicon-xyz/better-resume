# M3-T10 — M3 验收证据 + PROBLEMS 收口 + 简历草稿 + PR

- blocking：M3-T1..T9
- 纪律：证据必须是可复跑的命令输出，不是叙述

## 交付物

- docs/tickets/m3/ACCEPTANCE.md：
  1. §12.4 验收对照（并发同 key 单次调用 —— 后端并发用例 + 真模型冒烟双重证据）
  2. **真模型冒烟记录**：apps/api/scripts/resilience_smoke.py
     - 并发 5 个同 key 评分 → 上游调用计数、耗时、/resilience/stats 快照
     - 故障注入（本地假 gateway 连续失败）→ 熔断开态 → 后续请求 503 且上游 0 次 →
       假时钟推进 → 半开恢复
     - 限流：连打触发 429 与 Retry-After
  3. 本地 CI 全矩阵（与 workflow 同命令逐条 exit=0）
  4. 与提案的偏差清单（如实记录，含"发现但未修"的项）
- docs/tickets/m3/PROBLEMS.md：**实现中遇到的全部问题**（症状 / 根因 / 修法 / 证据），
  含 M2 key 缺陷、异步坑（task 泄漏、取消、背压）、假时钟相关坑、限流身份坑等
- docs/resume/M3-resume-draft.md（D14 硬规则：每个 M 更新一次简历草稿），
  重点是 D16 第一顺位亮点：单飞 + 熔断 + 限流 + 流式广播的具体数字
- README.md：M3 状态、参数表（settings）、统计端点说明
- PR：用 gh 建 PR → 双 job 绿 → 合并 → main 复跑绿（沿用 M1/M2 流程）

## 验收

| 命令 | 期望 |
| --- | --- |
| uv run pytest -q | 全绿（M2 324 → M3 目标 ≥ 380） |
| uv run ruff check . && uv run ruff format --check . | 干净 |
| uv run alembic check | 无待生成迁移（M3 预期无 schema 变更） |
| pnpm --filter web test --run 等前端四件 | 全绿 |
| gh pr checks | 双 job success |

## 不做

- 不做 M4 的语音、不做 M6 的分布式；不在本票里顺手重构无关模块。

