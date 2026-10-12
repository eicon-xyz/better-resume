# V4 证据：第二家 LLM 平台真机（阿里云百炼 DashScope / qwen-plus）

- 时间：2026-09-14（CST）；栈：compose \`nginx + 2×api + worker + postgres + redis\`
- 平台：阿里云百炼 **DashScope 兼容模式** \`https://dashscope.aliyuncs.com/compatible-mode/v1\`，模型 \`qwen-plus\`
- 接入方式：**零代码**——插一行 \`ai_models\` + \`PUT /api/v1/scenes/{scene}\`（compose 新增透传 \`BR_DASHSCOPE_API_KEY\`）
- 命令：\`uv run python -m scripts.real_model_smoke --base-url http://127.0.0.1:8080 --json /tmp/v4-dashscope2.json\`

## 1. 平台接入（没有任何业务代码改动）

\`\`\`sql
INSERT INTO ai_models (name, provider, base_url, model_id, api_key_env, extra, ...)
VALUES ('qwen-plus', 'dashscope', 'https://dashscope.aliyuncs.com/compatible-mode/v1', 'qwen-plus',
        'BR_DASHSCOPE_API_KEY', '{"stream_usage": true}'::jsonb, ...);
\`\`\`

- 预检：\`GET /compatible-mode/v1/models\` → **200，250 个模型**；\`qwen-plus\` / \`qwen-turbo\` / \`qwen3-max\` /
  \`deepseek-v3\` 均返回 200（说明百炼账号已开通，无需充值）。
- 五个场景全部 \`PUT\` 到 \`qwen-plus\` → 下一次调用即生效；跑完已恢复为默认 \`deepseek-flash\`。
- **diff 只有 compose 里一行环境变量透传 + 一条 SQL**：\`OpenAICompatAdapter\` 一行未改（除 §3 的 P19 修复）。

## 2. 四链路真机（qwen-plus）

\`\`\`json
{"steps": 9, "failed": [], "total_ms": 60601.7, "models": ["qwen-plus"], "total_tokens": 70}
\`\`\`

| 步骤 | 耗时 | 结果 |
| --- | --- | --- |
| login | 46 ms | 200 |
| chat-stream | 1818 ms | 94 字；\`usage={total 70, completion 52, prompt 18}\`；\`model=qwen-plus\` |
| question-extraction | **21799 ms** | 3 题，\`resume_score=87.0\`，字段齐全（qwen-plus 出题明显慢于 DeepSeek 的 8.4s） |
| answer-1 | 9176 ms | score 45.0 → 追问 |
| answer-1-F1 | 7975 ms | score 42.0 → 再追问 |
| answer-1-F2 | 6647 ms | score 35.0 → \`FOLLOW_UP_LIMIT_REACHED\` |
| answer-2 | 8063 ms | score 45.0 → 追问 |
| finish | 22 ms | overall 41.8、6 个 turn、\`summary_pending=true\` |
| report-summary(worker) | 5057 ms | 205 字总结（比 DeepSeek 那次的 25 字详细得多） |

**与 DeepSeek 的对照**（同一脚本、同一栈、同一代码路径，只换 base_url/model_id）：

| 指标 | DeepSeek \`deepseek-flash\` | 百炼 \`qwen-plus\` |
| --- | --- | --- |
| chat 首帧 p50（c=2 压测） | 1197 ms | **505 ms** |
| chat 流总时长 p50 | 1922 ms | 14071 ms（**仅 3 个流完成**：qwen 生成长、单流 ~14s） |
| 出题耗时 | 8382 ms | 21799 ms |
| 评分耗时 | 4.5–6.6 s | 6.6–9.2 s |
| 总结字数 | 25 字 | 205 字 |
| 字段集合差异 | — | **无**：两次运行的事件类型、Pydantic 校验、\`meta\` 帧结构完全一致 |

结论：**换平台只改了配置**；两家在字段/事件层面完全同构，差异只在速度与输出风格。首帧 qwen 更快、
整体生成更慢更长——这正是"容量数字必须分平台记录"的理由（\`docs/perf/M6-capacity.md\` §2.4 已注明）。

## 3. 过程中发现并修掉的一个缺口（P19）

第一次跑 \`chat-stream\` 步骤 **没有 \`meta\` 帧**（\`models: []\`、\`total_tokens: 0\`）：百炼的流式响应
默认不带 \`usage\`，而 DeepSeek 会带——我们的 token 统计与 \`event: meta\` 因此在这类平台上静默为空。
修法：把"请求 usage"做成**按模型行开关**（\`extra.stream_usage=true\` → 发送
\`stream_options={"include_usage": true}\`），默认关闭以免不认该字段的厂商 400。修后同一命令拿到
\`usage={total 70, ...}\`（见 §2）。测试：\`tests/llm_gateway/test_openai_compat.py\`
（配置了才发、非流式不发）。

## 4. 多副本复证（P18 修复）

\`PUT /api/v1/scenes/chat\` → \`deepseek-flash\` 后**交替**打流：

\`\`\`
t=0.9s instance=4ea595 model=deepseek-flash
\`\`\`

即两个副本都在 **≤1s** 内改用新绑定（TTL=5s 是上界）。P18 的修复在第二家平台下同样成立。

## 5. 错误面（真机）

把 \`chat\` 绑到一个**不存在**的百炼模型（\`definitely-not-a-real-model\`，同一把 key）：

\`\`\`
stream -> 200 event: error
data: {"message": "invalid at stage=chat: vendor returned 404: {\"error\":{\"message\":\"The model
      \`definitely-not-a-real-model\` does not exist or you do not have access to it.\", ...}}"}
\`\`\`

读法（与文档一致，不是 bug）：**"场景没配好"在开始流之前就返回 503**（V1 已验）；**供应商在流中途报错**
则以 \`event: error\` 帧交付，HTTP 仍是 200（SSE 语义如此），客户端拿到可读原因与 \`stage\`。
未验证：百炼限流 429 的真机表现（本轮并发 ≤2 未触发）。

## 6. 结论

- **零代码接入第二家真平台成立**，四链路全通、字段同构、错误三态映射一致；
- 差异是**平台特性**（速度、输出长度、是否默认带 usage）——后者暴露了 P19 并已修；
- 未做：不把默认供应商改成 qwen；不做百炼侧参数调优；星辰真机仍为备选（未申请凭据）。
