# M4-T11 — M4 验收证据 + PROBLEMS 收口 + 简历草稿 + PR

- blocking：M4-T1..T10
- 纪律：证据是可复跑的命令输出，不是叙述

## 交付物

- `docs/tickets/m4/ACCEPTANCE.md`：
  1. §12.4 验收对照（语音答题全流程：契约级证据 + 真机证据，两者分开写清）
  2. 句池归并（亮点③）的算法证据：关键分支的输入/输出样例表
  3. media 冒烟输出（`media_smoke.py`，scripted 与真机两种模式）
  4. 本地 CI 全矩阵（12 条命令逐条 exit=0）
  5. **未验证项清单**（讯飞真机 / 浏览器人工项 / 网络依赖）——不允许含糊
  6. 与提案的偏差清单
- `docs/tickets/m4/PROBLEMS.md`：**实现中遇到的全部难题与解决办法**（症状/根因/修法/证据），
  预计涵盖：浏览器 autoplay、AudioWorklet 采样率、PCM 半帧、rpl 区间语义、WS 背压/重连、
  edge-tts 网络与音色、ticket 时序、音频权限等
- `docs/resume/M4-resume-draft.md`（D14）：亮点③ 句池归并 + 语音全链路的可讲数字
- `README.md`：M4 状态、media 环境变量、WS 端点与 tts 端点说明
- PR：gh 建 PR → 双 job 绿 → 合并 → main 复跑绿

## 验收

| 命令 | 期望 |
| --- | --- |
| `uv run pytest -q` | 全绿（M3 415 → M4 目标 ≥ 470） |
| `uv run ruff check . && uv run ruff format --check .` | 干净 |
| `uv run alembic check` | 干净（M4 预期无 schema 变更；若加 media 表需迁移则如实记录） |
| `pnpm -C apps/web test --run` 等前端四件 | 全绿（115 → ≥ 145） |
| `gh pr checks` | 双 job success |

## 不做

- 不做 M5/M6 的内容（星云 adapter、分布式、压测）；不在本票顺手重构无关模块。

