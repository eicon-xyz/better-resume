# M5-T6 — 四条链路按场景解析（服务层零改动）

- blocking：M5-T2 T4
- 纪律：先写失败测试（红），再实现（绿）；**验收方式之一是"服务层文件不出现在 diff 里"**

## 目标

把"用哪个供应商"的决策从 HTTP 层的 `_resolve_gateway(model_ref)` 换成
`SceneResolver.resolve(scene)`：五个场景各取自己的绑定。这是 M5 的核心验收——
**换供应商不改业务码**。

## 交付物

- `http/chat.py`：聊天流按 `LlmScene.CHAT` 解析（模型选择器仍然可以覆盖：显式 model_ref 优先，
  留空则用场景绑定 —— 保证 M1 的"选模型"功能不退步）
- `http/interview.py`：出题 / 评分 / 追问 / 报告总结分别按
  `QUESTION_EXTRACTION` / `ANSWER_EVALUATION` / `FOLLOW_UP` / `REPORT_SUMMARY` 解析
- `interview_engine/*`、`chat/service.py`、`llm_gateway/adapters/openai_compat.py`**不改**
  （diff 里只应出现 http 层与 llm_gateway 的新文件）
- 测试：`tests/test_scene_routing.py`（≥8 例）：
  - 每个端点用假 gateway 记录"哪个场景解析到了哪个 gateway"（用 resolver 的测试替身注入）
  - 同一场景把绑定切到 xingyun（本地假服务端）→ 端点仍然工作，响应形状不变
  - 显式 model_ref 覆盖场景绑定（聊天链路）

## 测试

| 用例 | 断言 |
| --- | --- |
| 出题走 extraction 绑定 | 端点在 extraction 场景解析 gateway |
| 评分/追问/报告 | 各走自己的场景 |
| 聊天 | 默认走 chat 绑定；显式 model_ref 时覆盖 |
| 切换供应商 | 把 extraction 切成 xingyun（假服务端）→ 上传简历出题成功，返回结构不变 |
| 未配置 | 场景绑定缺密钥 → 503 + 明确错误（不是 500） |
| 回归 | 现有 chat/interview 全部用例不改一行仍然绿 |

## 验收

| 命令 | 期望 |
| --- | --- |
| `uv run pytest -q tests/test_scene_routing.py` | 全绿 |
| `git diff --name-only` | 服务层文件（interview_engine/、chat/service.py、adapters/openai_compat.py）不在列表里 |
| `uv run pytest -q` | 全量绿（M4 473 → +新增） |

## 不做

- 不改 M2 的状态机/幂等/题级锁；不改 M3 的韧性链；不为星云单独开代码路径。

