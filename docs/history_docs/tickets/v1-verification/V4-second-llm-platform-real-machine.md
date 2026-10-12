# V4 — 第二家 LLM 平台真机：阿里云百炼（DashScope 兼容模式，原方舟/星辰）

- blocking：需要一个 **阿里云百炼（DashScope）API key** 并在百炼**开通至少一个文本模型**
- 纪律：证据里写明实际用的是哪家；与 DeepSeek 只做**同代码路径**的对照，不假装是同一家

## 为什么改用阿里（2026-09-14 决策）

火山方舟 key 有效（\`GET /models\` 200，列出 40 个当前模型）但账号**未开通任何模型**，每个 chat 调用都是
\`404 ModelNotOpen\`；用户未在方舟充值 → 改用阿里云百炼（新用户通常有免费额度，无需先充值）。
星辰（讯飞）需要 key/secret + 每场景 flow_id，暂作第三家备选。

## 目标

1. **零代码**接入第二家平台：插一行 \`ai_models\`
   （\`base_url=https://dashscope.aliyuncs.com/compatible-mode/v1\`、\`api_key_env=BR_DASHSCOPE_API_KEY\`、
   \`model_id\` 取百炼里已开通的模型，例如 \`qwen-plus\` / \`deepseek-v3\`）→ \`PUT /api/v1/scenes/{scene}\`
   把场景指过去 → 下一次调用即生效；
2. 在真机跑 **M5 的 10 条 vendor 无关契约**（同一套用例 × 第二个真后端）+ 一次完整面试流程；
3. 与官方 DeepSeek 做**同 prompt 对照**（同一个 \`OpenAICompatAdapter\`、只换 base_url/model_id），
   证明"换平台不发版"；
4. 顺带验证 P18 的修复：\`PUT\` 之后**两个副本**都在 5s 内改用新绑定（真机复跑）。

## 交付物

- \`docs/tickets/v1-verification/V4-EVIDENCE.md\`：
  - 鉴权与模型列表（脱敏）、\`GET /models\` 结果
  - 绑定切换前后各一次真机调用摘要（model / usage / 耗时）
  - 10 条契约用例在百炼上的结果（同一套断言，失败就写失败）
  - 与 DeepSeek 的字段集合差异表（**只记录，不自动兼容**）
  - 错误面：错 key → 401/403；未开通模型 → 明确错误码；限流 → 429 行为
- \`apps/api/scripts/adapter_smoke.py\`：\`--real-dashscope\`（把现有契约模式参数化到任意 base_url + key）
- 若星辰可用：同一文档追加一节，**不改**现有 \`XingyunWorkflowAdapter\`

## 测试与验收

| 用例 | 断言 |
| --- | --- |
| 平台接入 | 插一行 + 改绑定即可用；**没有为百炼改业务代码**（diff 仅 SQL / 环境变量） |
| 四链路 | 出题 / 评分 / 追问 / 总结 在百炼上全部过 Pydantic 校验（\`response_format: json_object\` 被拒时靠提示词 + 重试也要过） |
| SSE 归一 | 事件类型只出现 \`ContentDelta/ReasoningDelta/VendorMeta/Done\` |
| 契约 | M5 的 10 条用例全绿；失败项如实记录 |
| 多副本 | \`PUT /api/v1/scenes/{scene}\` 后两个副本都在 ≤5s 内用新绑定（P18 修复的真机复证） |
| 对照 | 与 DeepSeek 的差异表 ≤1 页，每条给"接受/拒绝"结论 |

## 不做

- 不把默认供应商从 DeepSeek 换掉；不做百炼侧参数调优；不引入第三家托管编排（星辰除外，备选）

## 预估

用户给 key 后 **0.5 会话**（零代码）；若追加星辰真机则再 +1 会话。
