# 简历草稿（M1 对话里程碑）

> D14 硬规则：每个里程碑结束更新一次简历草稿。
> 口径原则：**只写已经跑通、可演示的东西**。M1 的对外物 = 打字机对话 + reasoning 面板 + 历史回放。

## 1. 本阶段新增条目（有执行证据）

- **多模型网关（亮点④ 的落地形态）**：自研 `llm-gateway` —— 数据库驱动的模型注册表
  （换模型/启停不用发版）、OpenAI 兼容适配器（一次实现吃 DeepSeek 等供应商）、
  `response_schema` 结构化输出强校验（失败重试 → 降级为显式错误）、失败三态分类
  （可重试 / 不可重试 / 供应商）、超时与指数退避、token 计量（含 reasoning tokens）、
  最小 prompt 注入防御。**密钥只以环境变量名入库**。
- **SSE 流式对话链路（承接旧简历「FastAPI + SSE + 15s 心跳」）**：`POST /chat/sessions/{id}/stream`
  归一 `content / reasoning / meta / done / error` 五类事件；15s 心跳用「生产者任务 + 队列」实现，
  心跳不会取消上游生成；客户端断开（`CancelledError`）与消费者提前关闭（`GeneratorExit`）
  两条路径都会把半截答案落库，历史永远完整。
- **reasoning_content 分流**：模型思考过程独立通道展示为「深度思考」折叠面板，
  与正文互不干扰（对应旧项目 DeepSeek reasoning 分流，但协议与渲染都重写过）。
- **确定性消息序号**：消息 seq 由 Postgres 事务 + 会话行锁分配（唯一索引兜底），
  **替掉了旧项目的 Redis Lua 分配器**；同 key 重投只落一条（幂等）。
- **契约即代码（D17）**：后端 OpenAPI 是唯一 Schema 源，前端类型 `schema.d.ts` 由
  `openapi-typescript` 生成，CI 双侧漂移检查——根治「前端猜字段」。
- **前端数据流修正**：服务端状态只进 TanStack Query，运行态才进 zustand；
  SSE 解析器（跨 chunk 分帧/脏帧/心跳）与打字机 limiter 都有直接单测（旧项目这里是测试空白）。

## 2. 数字（可复核）

| 指标 | 值 |
| --- | --- |
| 后端测试 | 94 passed（真 Postgres；对 LLM 只 mock HTTP 边界 + 录制回放样本） |
| 前端测试 | 65 passed（api-client 20 / renderer 6 / 组件 7 / 状态层 14 / 页面 6 / 其它） |
| 真实调用验证 | 流式 25–41 帧、reasoning 0–12 帧、结构化输出 `parsed=Answer(answer='ok')` |
| 单条链路延迟 | 首帧 < 2s（本机 + 代理，实测） |

## 3. 与旧简历的承接对照

| 旧简历条目 | 新承接物（M1 已落地部分） |
| --- | --- |
| LLM 统一工厂层（DeepSeek/Claude 切换） | llm-gateway 模型注册表 + 运行时切换（Claude 明确不进默认清单） |
| FastAPI + SSE + 15s 心跳 | chat SSE 链路 + 事件归一 + 心跳不干扰生成 |
| Agent 追问不编造数据 | （M2 承接）结构化输出强校验已在 M1 就位 |
| 五阶段 Prompt Pipeline | （M2 承接）状态机 + 每阶段独立可测 |

## 4. 下一里程碑要补的证据（M2）

面试引擎：`resume-parser` 混合解析（pdfplumber + 章节启发式 + CJK 回退）→ 出题 →
答题 → 评分 → 追问裁决纯函数 → 报告/雷达图；以及 ai-resilience 的单飞 + 熔断 + 限流（M3）。
