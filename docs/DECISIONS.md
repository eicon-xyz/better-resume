# better-resume 技术栈与范围决议记录

> 产生方式：对 AI-Meeting（码上面试平台）的深度架构分析（见 docs/ai-meeting-architecture-analysis.md）
> 之后的专项技术选型评审，三轮 grilling 逐项拍板。本文档是新仓库的**开工依据**，
> 与分析文档 §11/§12 一致；冲突时以本文档为准。

---

## 0. 一句话定位

把 AI-Meeting（Spring Boot 模拟面试平台）重写为**作品集替换项目**：
Python/FastAPI + React，完整度高于旧项目，且旧简历（Resume Section Optimizer）的每一条
亮点在新项目中有明确承接物。

---

## 1. 决议表（D01-D18）

| # | 决议 | 内容 |
| --- | --- | --- |
| D01 | 项目定位 | 求职作品集项目，**替代** Resume Section Optimizer 且完整度更高；派生「亮点继承约束」：旧简历每条亮点必须有新承接物 |
| D02 | 后端框架 | Python 3.12 + FastAPI + **SQLAlchemy 2.0 async** + Alembic 迁移；async_sessionmaker 挂 lifespan，全项目统一 get_session 依赖 |
| D03 | 存储 | **Postgres（关系表 + JSONB）+ Redis 双件套**；砍掉 Mongo（消息/快照/记录入 JSONB，GIN 索引），消除原项目跨三库非原子的坏味道 |
| D04 | LLM 编排 | **自研轻量编排**：表驱动状态机 + 追问裁决纯函数 + openai 兼容 SDK 直连 + Pydantic response_schema 强校验；**不引 LangChain**；保留 XingyunWorkflowAdapter 作第二 adapter（真接缝，非死代码） |
| D05 | 前端 | React 19 + **Vite SPA** + TanStack Query + **zustand**（砍 Redux）+ shadcn/ui；移植原项目 lib 四件套（request/streamLimiter/audioTranscription/errors）与 controller-hook 模式 |
| D06 | 语音供应商 | ASR **保留讯飞 AST**（pgs/rg/seg_id 句池归并算法移植为 Python，独家亮点）；TTS 用 **edge-tts** 起步 + TtsSynthesizer adapter 留位 |
| D07 | 部署 | 单机 docker compose（api + worker + postgres + redis + nginx）；**分布式单飞只留接口不写 Lua 实现**（诚实原则，吸取原项目「默认关闭的死代码韧性」教训） |
| D08 | 仓库形态 | Monorepo：apps/api（Python/uv）+ apps/web（TS/pnpm）+ docs/ + skills/ |
| D09 | 范围裁剪 | **砍**：神态分析（摄像头/表情）、独立 Agent 会话模块。**留**：面试全链路（出题→答题→评分→追问→报告/雷达图）、AI 对话（reasoning_content 分流）、ASR 语音答题、TTS 题目播报。会话收敛为 chat + interview 两种，统一 conversation 模块 |
| D10 | 简历解析 | **自建混合解析器**：pdfplumber 提文本 → 章节启发式（关键词/字号/加粗特征打分 + CJK 回退）→ Pydantic ResumeContext → LLM 只在其上出题。分工哲学：解析不靠 LLM（可测可控），出题才靠 LLM（反幻觉） |
| D11 | 认证 | **HttpOnly Cookie session**（Redis 存储、30 天滑动过期）+ **WS 握手一次性 ticket**；翻转原项目 localStorage/URL token 的 XSS 面；单体同域不用 JWT |
| D12 | 模型注册 | 保留 DB 表 + /models 端点 + 运行时切换（管理端启停）；默认 **DeepSeek-V3**（对话/出题/评分）+ **DeepSeek-R1**（展示 reasoning_content 分流）；Claude 不进默认清单 |
| D13 | skills 知识库 | 轻量复刻原项目实践：repo-map（模块路由）+ 每个深模块一个 SKILL.md（不变量+陷阱）+ 自动生成 API 索引脚本 |
| D14 | 里程碑 | M0→M6 顺序推进（见分析文档 §12.4），6-8 周业余时间；**硬规则：每个 M 结束更新一次简历草稿** |
| D15 | 语音交互范围 | 一个转写通道、两个消费方（面试答案框 + 对话输入框）、一个播放器；**砍草稿板** |
| D16 | 简历亮点排序 | 深挖 trio：**① ai-resilience（单飞+熔断+限流，假时钟测试）② interview-engine（状态机+幂等+裁决）③ ASR 句池归并增量去重**；支撑 bullet：④ llm-gateway（多模型注册+schema 防幻觉）⑤ resume-parser（混合解析） |
| D17 | 工程微默认 | uv / pnpm；structlog（JSON + request_id，**不引 OpenTelemetry**）；测试先行、只 mock 系统边界（LLM/时钟/Redis/讯飞）；GitHub Actions 双 job（ruff+pytest+alembic check / eslint+tsc+vitest）；**OpenAPI → TS 类型生成**（openapi-typescript，根治前端猜字段）；MIT |
| D18 | 开发流程 | 五阶段 **grill → spec → implement → review → retro**（Matt Pocock 技能集，2026-09-23 起）：grill 逐轮拷问并即时把术语落进 `CONTEXT.md`、把决策落进本文；spec = `docs/tickets/<stage>/README.md`（即原「阶段提案」）；implement 驱动 `/tdd` 垂直切片、收尾自动 `/code-review` 双轴评审；retro 读会话日志改环境。**人工闸门不变**：spec 经用户点头才动工、验收包由用户验收、AI 不擅自合并。配置见 `docs/agents/`（本地 markdown tracker，映射 `docs/tickets/`） |

---

## 2. 亮点继承约束映射（D01 的落实）

| 旧简历亮点（Resume Section Optimizer） | 新项目承接物 | 承接方式 |
| --- | --- | --- |
| 五阶段 Prompt Pipeline（每步独立调试） | interview-engine 编排链 | 形态升级：状态机 + 每阶段独立可测 |
| Agent 追问机制（不编造数据） | 追问裁决纯函数 + maxFollowUp + missing_points | 天然覆盖，且加 schema 强校验 |
| FastAPI + SSE + 15s 心跳 | SSE/WS 三链路 | 直接平移 + 升级（WS 音频） |
| LLM 统一工厂层（DeepSeek/Claude 切换） | llm-gateway 模型注册表 | 升级：运行时切换 + schema 校验 + 注入防御 |
| 混合策略简历解析器 | resume-parser（D10） | **新增模块**，算法平移 |

---

## 3. 明确不做清单（防范围蔓延）

神态分析 / 独立 Agent 会话模块 / 草稿板 sketchpad / 分布式 Lua 单飞实现 / LangChain 全家桶 /
JWT / OpenTelemetry / Next.js / MongoDB / 第三家默认模型 / Claude adapter（默认清单外）。

---

## 4. 开工指引（新会话用）

1. 先读 docs/ai-meeting-architecture-analysis.md：§3 架构形状 → §4.1 interview 模块（状态机/
   幂等/单飞/恢复）→ §12 蓝图（模块接口签名级设计 + 里程碑）。
2. 本仓库当前只有 docs/；应用代码从 **M0** 开始：monorepo 骨架 + compose + CI +
   六个后端模块空接口 + 失败测试（TDD）。
3. 测试纪律沿用：先写失败测试再实现；只 mock 系统边界。

## 5. 参考文档

- docs/ai-meeting-architecture-analysis.md —— 原项目全景架构分析（13 章、10 图、75 端点）
