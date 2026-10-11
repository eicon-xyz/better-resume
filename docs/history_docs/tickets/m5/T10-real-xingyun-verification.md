# M5-T10 — 真机验证：真星云工作流（需凭据）

- blocking：M5-T3 T6
- 纪律：**没有凭据就不写"已验证"**；结论必须附命令输出

## 目标

把 T3/T4 的代码路径接到真实星云工作流上，产出可复核的真机证据，并记录与文档样本的差异
（尤其是 **SSE 形状与输出字段名** —— 这正是旧项目"契约靠猜"的来源）。

## 交付物

- 凭据接入：`XINGCHEN_API_KEY` / `XINGCHEN_API_SECRET` / 每场景 `XINGCHEN_FLOW_ID_*`
  （只在 gitignored `.env`；`.env.example` 只写变量名；绑定行的 `target_ref` 存 flow_id，不存密钥）
- `uv run python scripts/adapter_smoke.py --provider xingyun --real-xingyun --scene question_extraction`
  与 `--scene answer_evaluation`：真机调用，打印请求/响应摘要与 schema 校验结果
- `docs/tickets/m5/ACCEPTANCE.md` 单列"真机验证"章节：
  - 真实 SSE 帧样例（截断脱敏）与我们解析器的对应关系
  - 真实输出字段名 vs 我们 schema 的差异清单（**差一个就改映射表，不改别名回退**）
  - 结论：可切换 / 需调整映射 / 不可用，三选一，附证据

## 测试

| 用例 | 断言 |
| --- | --- |
| 真机鉴权 | Bearer 头被接受（无 401/403） |
| 出题场景 | 真工作流返回可解析的 `QuestionBatch`（resume_score 在 0-100） |
| 评分场景 | 真工作流返回可解析的 `ScoreResult`（score 在 0-100，missing_points 为列表） |
| 差异记录 | 文档样本与真机样本的差异逐条列出（无差异也要写"无"） |

## 验收

| 命令 | 期望 |
| --- | --- |
| `uv run python scripts/adapter_smoke.py --provider xingyun --real-xingyun` | 有凭据：真实响应 + 校验通过；无凭据：明确提示缺哪些变量并退出码 2 |
| 文档 | ACCEPTANCE 的"未验证项"章节删除对应条目，或写明仍未验证的原因 |

## 不做

- 不做星云侧提示词调优；不做多工作流版本兼容；不做压测（M6）。

