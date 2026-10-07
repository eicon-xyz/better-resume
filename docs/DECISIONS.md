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

## 1. 决议表（D01-D22）

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
| D18 | 开发流程 | 五阶段 **grill → spec → implement → review → retro**（Matt Pocock 技能集，2026-09-23 起）：grill 逐轮拷问并即时把术语落进 `GLOSSARY.md`（D21 改名；D18 原文写的是 `CONTEXT.md`）、把决策落进本文；spec = `docs/tickets/<stage>/README.md`（即原「阶段提案」）；implement 驱动 `/tdd` 垂直切片、收尾自动 `/code-review` 双轴评审；retro 读会话日志改环境。**人工闸门不变**：spec 经用户点头才动工、验收包由用户验收、AI 不擅自合并。配置见 `docs/agents/`（本地 markdown tracker，映射 `docs/tickets/`） |
| D19 | 分布式限流与降级语义 | 限流状态迁到 Redis（Lua 令牌桶，单次 `eval` 原子；键 `br:rl:{bucket}:{identity}`，TTL 兜底过期），**N 副本共享同一份对外配额**。只共享供应商成本桶（`AI_CALL/ANSWER/HEAVY`）——它们限的是对外配额；`GENERAL/READ` 留在进程内：它们限的是「我们自己的容量」，副本变多容量也变多，按副本限才是对的（P7）。时间基线用**应用侧注入的 wall-clock**（`SystemClock` 是 monotonic，跨进程不可比；Lua 只做算术，负 elapsed 钳 0）。**降级语义**：Redis 不可用时退回进程内桶（配额暂时 ×N，即迁移前的语义），并显式可观测——`ratelimit_degraded` 日志 + `/resilience/stats` 计数 + 响应头 `X-RateLimit-Scope: shared\|instance`，外加 30s 冷却窗口（窗口内不再尝试 Redis）与 50ms 单次超时；**不 fail-closed**（限流不是正确性，Redis 抖动不该升级成全站 503），**不按快照拒绝**（跨副本快照本就不准，只会更严不会更准）。对外语义不变：`X-Instance-Id`、429 映射、白名单、身份哈希照旧 |
| D20 | 桶算术的双实现与等价契约 | 限流桶的补充/扣减算术**保留两份实现**：Redis 侧 Lua（`redis_buckets._TAKE_LUA`，跨副本读改写必须一次 `eval` 原子完成）与进程内 `TokenBucket`（降级路径不能依赖 Redis，见 D19）。二者**不可归约**，因此不追求「合并成一份」，而是把「必须永远一致」变成可执行断言：`take_lua_math` 是 Lua 算术的**可执行镜像**（运算顺序与 Lua 字面一致——`elapsed / 1000 * rate` 与 `elapsed * rate / 1000` 差 1 ULP），由 `tests/ai_resilience/test_ratelimit_equivalence.py` 用同一张场景表驱动两条路径、逐项且**按位**比较，外加一条「Lua 关键式仍在」的源码警报。**否决的替代**：删 Lua 改成 Python 侧 RMW（要 WATCH/MULTI 重试或接受非原子读改写，属行为变更）；把 `lupa` 加进依赖以便用 fakeredis 真执行 Lua（原生依赖 + CI 走 `uv sync --frozen`，须单独提案）；模板生成 Lua（CI 里同样执行不了，等于把风险换个地方藏）。**已知边界**：本环境无法执行 Lua，「等价」是「镜像 ↔ TokenBucket 可执行且按位」＋「Lua 文本警报」，**不含 Redis 端真实执行验证**；Lua `tostring`（%.14g）往返有 ~1e-14 尾差；键 TTL 与进程内 `max_identities` 是两种过期策略，不要求等价。**纪律**：改任一侧算术必须两处同改，否则等价测试会红。审计条目 ai-02 |
| D21 | 文档落点：术语表与 ADR | 域词汇表用仓库根 **`GLOSSARY.md`**，**取代** D18 里写的 `CONTEXT.md`——与技能默认文件名对齐，少一个自定义名；ADR 仍用仓库既有的 **`docs/DECISIONS.md` 续编 D 号**（不建 `docs/adr/`），因为决议表已是本仓库单一权威，且被票据/验收包互相引用。词汇表只收本仓库特有的**产品域**与**工程过程**词（分两节），**不含实现细节**（Lua / TokenBucket 这类属实现，不进词汇表）；`docs/agents/domain.md`、`AGENTS.md` 的指针同步改。首次落地（2026-10-06）收 **31 词 / 7 节**：面试（7）、会话与消息（3）、语音（3）、模型与场景（3）＋ 阶段与文档（4）、验证（9）、配额与降级（2） |
| D22 | 验证证据的判定权 | 「验证过」必须由**会变红的检查**背书，分三级：(1) **CI 的 scripts 层只跑结构级核对**——审计 JSON 字段齐全 + 引证指向存在的行区间（`verify_audit_evidence.py --structural`），这一级**不因代码漂移变红**（实测：对 `http/chat.py` 纯插 3 行 → 4 条引证变 partial；`--strict` 退 1、`--structural` 退 0）；(2) **`--strict` 逐字级核对降为审计/修复收口的手动门槛**（引证窗口里必须真有原文摘录）；(3) 判断项规则落 `CODING_STANDARDS.md`——声称「我验证了 X」的脚本必须真检查退出码或断言，只打印结论的验证脚本视为缺陷。配套工具：`scripts/verify_mutation.sh`（断言基线绿 → 变异红 → 恢复绿，并校验恢复后 sha256 与改前一致）、`scripts/check_scripts.py`（两个脚本目录语法扫描，SyntaxWarning 当错误）、`.githooks/pre-commit`（可选，提交前挡刀）。**否决**：把 strict 放进 CI（无关重构变红＝教人绕过它）；只靠自述证据（曾有一个恒退 0 的「证明脚本」从全绿 CI 里溜过） |

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
