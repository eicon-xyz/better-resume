# M5-T8 — 双供应商端到端对照（同一场景跑两遍）

- blocking：M5-T6
- 纪律：证据票；先写脚本让它红（缺数据），再补齐

## 目标

用同一条真实链路（上传简历 → 出题）与同一条结构化链路（评分）分别跑
`openai_compat`（真 DeepSeek）与 `xingyun`（本地假服务端；有凭据时切真机），
输出**对照表**：请求形状、响应形状、耗时、schema 校验结果、错误分类。

## 交付物

- `apps/api/scripts/adapter_smoke.py`：
  - `--provider openai_compat|xingyun|both`；`--scene question_extraction|answer_evaluation|...`
  - xingyun 默认连本地假服务端（`--xingyun-url`），带 `--real-xingyun` 时读环境变量连真机
  - 输出：每个 provider 的请求摘要（脱敏）、响应摘要、耗时、`parsed` 的字段、失败分类
  - 断言：同一场景两条路径的**输出 schema 完全一致**（字段名集合相同）
- `docs/tickets/m5/ACCEPTANCE.md` 的"对照表"章节（由脚本输出粘贴，标注日期与环境）
- 测试：`tests/test_adapter_parity.py`（≥4 例）：同一输入的两种 provider 输出都能通过同一 schema；
  字段名不一致时用例转红

## 测试

| 用例 | 断言 |
| --- | --- |
| 输出 schema 一致 | 两个 provider 的 `parsed` 字段名集合相同 |
| 业务码零改动 | 服务层对两个 provider 的行为一致（用同一服务 + 两个假 gateway 断言返回值结构） |
| 错误语义一致 | 两个 provider 的超时/校验失败映射到同一异常类型 |
| 切换生效 | 改绑定后解析到的 gateway 类型变化（端到端一次） |

## 验收

| 命令 | 期望 |
| --- | --- |
| `uv run python scripts/adapter_smoke.py --provider both --scene question_extraction` | 打印两条路径的对照表；真 DeepSeek 出题成功、假星云返回同 schema |
| `uv run pytest -q tests/test_adapter_parity.py` | 全绿 |
| 有星云凭据时 | `--real-xingyun` 跑通并记录与文档样本的差异（T10） |

## 不做

- 不做性能基准（M6 压测）；不做成本对比（两个供应商计费口径不同，容易变成假数字）。

