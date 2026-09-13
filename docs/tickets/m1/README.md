# M1 票据拆分提案（待确认）

> 依据：docs/DECISIONS.md（D03/D04/D05/D08/D09/D11/D12/D17）+ 分析文档 §4.2（原 ai 模块）、
> §5.3–5.7（前端 services/hooks/store/lib）、§6（数据模型）、§7.2（chat SSE 流）、§8（ai 端点）、
> §12.2（会话/网关接口）、§12.4（M1 里程碑）。
> 状态：**提案，等你确认后动工**。

## 1. M1 验收（§12.4 原文）

> conversation + llm-gateway(OpenAICompat) + chat SSE 页 → **打字机对话 + reasoning 面板 + 历史回放**

## 2. 范围边界

**做**：conversation 落库（Postgres+JSONB）、llm-gateway 的 OpenAIICompatAdapter 与模型注册表、
chat SSE 后端、OpenAPI→TS 类型生成、前端 api-client / stream-renderer / chat 页（打字机 +
reasoning 折叠面板 + 历史回放）。

**不做**（留后续里程碑）：interview-engine 与 resume-parser 实现（M2）、ai-resilience 的单飞/熔断/
限流（M3，M1 只留直通接缝）、media 语音（M4）、Xingyun adapter（M5）、分布式模式（M6）、
真实 users 表与登录页（见 Q3）、worker/nginx、skills 知识库、Markdown 以外的富文本/公式。

**纪律**：**从本里程碑第一张票据起，先写失败测试再实现（红-绿）**；只 mock 系统边界
（LLM HTTP / 时钟 / Redis / 讯飞），内部模块不 mock；小步提交说 WHAT；每票附执行证据。

## 3. blocking 图

```
T1 conversation 持久化 ──> T2 llm-gateway 核心 ──> T3 chat SSE 后端 ──> T4 OpenAPI→TS
                                                          │
   T7 设计基线（独立）                                     ├──> T5 api-client ──┐
                                                          └──> T6 stream-renderer ──> T8 运行态/数据层 ──> T9 chat 页面
 T7 ────────────────────────────────────────────────────────────────────────────────┘
 全部 ──> T10 M1 验收与文档
```

| 票 | 标题 | blocking | 预估 |
| --- | --- | --- | --- |
| T1 | conversation 持久化（表 + store + seq 原子性） | M0 | 1 会话 |
| T2 | llm-gateway：模型注册表 + OpenAICompatAdapter + schema 强校验 | T1 | 1.5 会话 |
| T3 | chat 后端 API：会话 CRUD + 历史 + SSE 流式 + 心跳 | T1 T2 | 1 会话 |
| T4 | OpenAPI → TS 类型生成 + CI 漂移检查 | T3 | 0.5 会话 |
| T5 | 前端 api-client（唯一网络接缝） | T4 | 1 会话 |
| T6 | stream-renderer（事件解析 + 打字机 limiter） | T4 | 0.5 会话 |
| T7 | 前端设计基线（tokens + 基础组件） | M0 | 0.5 会话 |
| T8 | chat 运行态与数据层（zustand + TanStack Query + controller-hook） | T5 T6 | 1 会话 |
| T9 | chat 页面（打字机 + reasoning 面板 + 历史回放） | T7 T8 | 1 会话 |
| T10 | M1 验收、文档与简历草稿 | 全部 | 0.5 会话 |

## 4. 本提案的形态基调（对应旧项目坏味道的修正）

1. **conversation 是消息唯一归属**：不再出现「chat 一套、interview 一套、agent 一套」三处三版
   （§9 坏味道）；表结构一次到位（kind ∈ chat|interview）。
2. **seq 不再用 Redis Lua**：Postgres 事务 + 会话行锁 + `UNIQUE(conversation_id, seq)` 兜底，
   少一个分布式件（D03 精神）。
3. **前端单一数据源**：服务端状态全交 TanStack Query，运行态才进 zustand——不再把 Query 结果
   手工 hydrate 进全局 store（§5.5 坏味道）。
4. **接缝即测试面**：SSE 解析器、limiter、错误归一都有直接单测（旧项目「SSE 解析器无单测」的空白）。

## 5. 待确认项

见 `OPEN-QUESTIONS.md`（10 项，其中 Q1 密钥、Q2 UI 库、Q3 登录范围会直接影响动工方式）。
