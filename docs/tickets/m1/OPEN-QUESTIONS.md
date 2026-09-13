# M1 待确认项（决策请拍板，我不自行决议）

## 0. 结论回填（2026-09-13 已拍板）

| 编号 | 你的决定 | 落地方式 |
| --- | --- | --- |
| Q1 | **提供了 DeepSeek API key** | 只写入本机 `.env`（已被 .gitignore 忽略，已用 `git grep` 验证零入库）；CI 永不使用；compose 通过 `${BR_DEEPSEEK_API_KEY:-}` 透传；**建议 M1 演示后轮换该 key**（它已出现在聊天记录里） |
| Q2 | **不保留 shadcn/ui 叙事** | 走自研 tokens + CSS Modules + 6 个原子组件（原提议 A） |
| Q3 | 照准 | M1 用 dev 会话入口，真实 users 表/登录页归 M2 |
| Q4–Q10 | 照准 | 幂等键 / 状态分工 / react-markdown + CSS 动效 / 40ms+15s / 不落 raw payload / 生成物入库 / 标题取首条 30 字 + 会话侧栏 |

### 0.1 实测事实（影响 T2 的模型注册表）

用你的 key 实际探测（2026-09-13）：

- `GET /models` 返回两个模型：**`deepseek-flash`**、**`deepseek-v4-pro`**
  —— 不是 D12 字面上的「DeepSeek-V3 / DeepSeek-R1」（供应商已改名），意图不变：一个快、一个强。
- 两个模型**流式与非流式都会返回 `reasoning_content`**，第一帧常是
  `{"content": null, "reasoning_content": ""}`（解析器必须同时容忍两个通道的空值）。
- SSE 帧格式：`data: {json}` + 结束帧 `data: [DONE]`。
- `response_format={"type":"json_object"}` 可用，返回 content 为 JSON 字符串，
  usage 里带 `completion_tokens_details.reasoning_tokens`。
- 原始样本已存为回放夹具：`apps/api/tests/fixtures/llm/`（3 个文件，已确认不含密钥）。

**待你追认（不阻塞动工）**：注册表种子用真实模型名 `deepseek-flash` / `deepseek-v4-pro`，
`supports_reasoning=true` 两个都置；如果你希望保留 V3/R1 的叙事命名，我把 `model_ref`
取名为 `deepseek-v3`/`deepseek-r1`、`model_id` 指向真实模型即可（一行种子数据的事）。

---
| 编号 | 一句话 | 我的提议 |
| --- | --- | --- |
| Q1 | 真实 LLM 调用的密钥与范围 | 环境变量 `BR_DEEPSEEK_API_KEY`；CI 永不真调用；本地可选 smoke 脚本 |
| Q2 | 前端 UI 方案 | M1 自研 tokens + CSS Modules（不引 shadcn/Tailwind） |
| Q3 | 是否现在做真实登录 | 不做，M1 用 M0 的 dev 会话入口；真实 users 表+登录页归 M2 |
| Q4 | 消息幂等 | 做 `client_message_id`，成本小、防重复计费 |
| Q5 | 状态分工 | 服务端状态只进 TanStack Query，zustand 只放会话内运行态 |
| Q6 | Markdown 与动效依赖 | 引 `react-markdown` + `remark-gfm`；动效用 CSS，不引 framer-motion |
| Q7 | 打字机与心跳参数 | 照旧项目：40ms/12 字、SSE 心跳 15s |
| Q8 | raw 响应落档 | 只记 usage/latency/finish_reason 到 structlog，不落原始 payload |
| Q9 | 生成物是否入库 | `openapi.json` + `schema.d.ts` 入库，CI 只做漂移检查 |
| Q10 | 会话标题与列表 | 标题取首条消息前 30 字（不调 LLM）；M1 有会话侧栏 |

---

## Q1 密钥与真实调用

事实：kickoff 红线是「任何真实密钥必须走环境变量」，M0 的 `.env.example` 已有 compose 开发默认值；
本机目前**没有** DeepSeek key。
提议：`ai_models.api_key_env` 只存环境变量名；密钥缺失时 `/api/v1/models` 返回
`configured: false`，聊天入口给诚实错误提示；CI 全部跑录制回放样本，永不真调用；
另给 `scripts/chat_smoke.py` 供你本地带 key 手动跑真实对话（不进 CI）。
**需要你定**：是否现在提供 key（提供后我可以在 T9 做一次真实端到端演示）。

## Q2 前端 UI 方案

D05 写的是 shadcn/ui，但 M1 只需 6 个原子组件（Button/Textarea/Card/Spinner/Collapsible/Empty）。
- 选项 A（提议）：自研组件 + CSS 变量 tokens + CSS Modules。依赖最少，样式没有隐式约定。
- 选项 B：现在就引 shadcn/ui（含 Tailwind）。组件更全，但 M1 用不到，且引入 Tailwind 会改写
  所有样式的写法；若你希望简历上有 shadcn/Tailwind 关键词，我照 B 做。

## Q3 登录范围

§12.4 的 M1 没提认证。M0 已有 dev 直发会话端点。
- 提议：M1 前端加一个「dev 登录卡」（输 user_id -> POST /auth/session），真实注册/登录/密码哈希/
  users 表放 M2（与简历上传的归属校验一起做，避免两次返工）。
- 例外：如果你希望 M1 就演示「真实登录」，我把它并成一张新票（+1 会话）。

## Q4 消息幂等

提议：`POST .../stream` 请求体带 `client_message_id`（uuid），同会话唯一索引；
重复投递只落一条 user 消息、不重复调用模型。前端在重试时复用同一 id。

## Q5 状态分工

对齐 §5.5 的修正：会话列表/历史/模型列表 = TanStack Query；当前流的消息/streaming/activeRequestId
= zustand；两者用 controller-hook 组装。不再把 Query 结果 hydrate 进全局 store。

## Q6 Markdown 与动效

提议：`react-markdown` + `remark-gfm`（聊天里代码块/列表很常见）；代码高亮、公式、图表留 M2+。
打字机光标与面板展开用 CSS；不引 framer-motion（旧项目用了，但我们不需要它带来的体积）。

## Q7 参数

`40ms / 12 字`（旧 streamLimiter）+ SSE 心跳 `15s`（旧项目 FastAPI+SSE 亮点）。
如果你想保留这两个数字作为简历叙事，我照原样；否则可以调大缓解长文本抖动。

## Q8 raw 响应

旧项目把 `rawResponseData` 落 Mongo 用于排查。提议 M1 只在 structlog 记
`model / latency_ms / usage / finish_reason`，不落原始 payload（避免把大对象塞进 JSONB 里）。
若你希望保留「原始响应可回放」这个能力，我加一张 `llm_raw_calls` 表（+0.5 会话）。

## Q9 生成物入库

提议：`apps/api/openapi.json` 与 `apps/web/src/api/schema.d.ts` 入库，CI 检查「重新生成后是否有
diff」，有 diff 即失败——契约变更在 PR 里肉眼可见。

## Q10 会话标题与侧栏

提议：创建会话时标题 = 首条用户消息前 30 字（不额外调 LLM）；M1 提供会话侧栏（列表 + 新建 +
重命名 + 删除）。若你想砍掉侧栏以缩短 M1，我把它移到 M2。