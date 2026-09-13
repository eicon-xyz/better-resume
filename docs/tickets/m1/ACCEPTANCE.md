# M1 验收证据（对话里程碑）

> 执行日期：2026-09-13 · 分支 `m1/chat-milestone` · 依据 docs/tickets/m1/（T1–T10）

## 0. 环境

| 项 | 值 |
| --- | --- |
| Python / uv | 3.12.14 / 0.12.7 |
| node / pnpm | v22.23.2 / 11.20.0 |
| 真实模型 | `deepseek-flash`（默认）、`deepseek-v4-pro`（registry 驱动，密钥只走环境变量） |

## 1. §12.4 的 M1 验收三条

### 1.1 打字机对话

- 前端：`src/stream/renderer.ts` 双通道 limiter（40ms / 12 字）+ 过期 chunk 双重校验；
  6 个假时钟用例（500 字突发 → 42 帧且拼接无损、stop 后零回调、stale 缓冲丢弃）。
- 端到端（compose 内、真实模型，`curl -N`）：

```
frames: content=29 reasoning=0 done=1
ANSWER: 哈希表是一种通过哈希函数把键映射到数组位置、从而实现平均 O(1) 时间插入、删除和查找的数据结构。
```

### 1.2 reasoning 面板

- 后端把 `reasoning_content` 归一为 `event: reasoning`（真实样本实测 12 帧）；
- 前端 `深度思考` 折叠面板默认展开、可收起（`aria-expanded` + `role=region`）；
- 页面级用例：streaming 中面板显示推理内容；不含推理的响应不渲染面板。

### 1.3 历史回放

- 后端 `GET /api/v1/chat/sessions/{id}/messages?before=&limit=`（seq 游标，升序返回）；
- 前端 `useInfiniteQuery` 分页（每页 50，页间倒序拼装）+「加载更早的消息」；
- 精确去重：历史行带 `client_message_id`，乐观 user 消息不会重复出现。

```
HISTORY: [(1,'user',12,reasoning=False,token_count=None), (2,'assistant',50,reasoning=False,token_count=127)]
（经 Vite 同源代理那条链路：content=25 / reasoning=12 帧，history 含 client_message_id='e2e-1'）
```

## 2. 本地 CI 矩阵（12 条命令全部 exit=0）

| # | 命令 | 结果 |
| --- | --- | --- |
| 1 | `uv sync --frozen` | exit=0 |
| 2 | `uv run ruff check .` | exit=0 |
| 3 | `uv run ruff format --check .` | exit=0 |
| 4 | `uv run pytest` | **94 passed** |
| 5 | `uv run alembic upgrade head` | exit=0 |
| 6 | `uv run alembic check` | No new upgrade operations detected |
| 7 | `uv run python scripts/export_openapi.py --check` | openapi.json is up to date |
| 8 | `pnpm install --frozen-lockfile` | exit=0 |
| 9 | `pnpm -C apps/web lint` | exit=0（0 error / 0 warning） |
| 10 | `pnpm -C apps/web typecheck` | exit=0 |
| 11 | `pnpm -C apps/web test` | **65 passed** |
| 12 | `pnpm -C apps/web check:api` | 生成物无 diff |

> 注意：第 1–12 条就是 `.github/workflows/ci.yml` 两个 job 的 run 步骤（见 §4）。

### 2.1 空库一致性（等价 CI 的起点）

CI 的 Postgres 是全新空库，而本地库是增量迁移出来的，因此单独验证了一次「空库 → 迁移 → 全量测试」：

```
$ createdb better_resume_ci
$ BR_DATABASE_URL=.../better_resume_ci uv run alembic upgrade head
Running upgrade  -> 0001_baseline
Running upgrade 0001_baseline -> b349260daa14   (conversations + conversation_messages)
Running upgrade b349260daa14 -> 745c366ba82b   (ai_models + 种子)
$ uv run alembic check        -> No new upgrade operations detected.
$ uv run pytest               -> 94 passed
```

表：`ai_models` / `alembic_version` / `conversation_messages` / `conversations`；
索引含 `ix_conversation_messages_meta`（GIN jsonb_path_ops）、
`uq_conversation_messages_conversation_id_seq`、`uq_conversation_messages_client_message_id`（部分唯一）。

## 3. compose 三服务（重建后跑 M1 代码）

```
$ docker compose up -d --build --wait
SERVICE    STATUS
api        Up (healthy)    0.0.0.0:8000->8000/tcp
postgres   Up (healthy)    0.0.0.0:5432->5432/tcp
redis      Up (healthy)    6379/tcp          <- 不发布宿主端口（D-C）
```

`GET /api/v1/models` 在 compose 内返回两个模型且 `configured: true`（密钥经 `${BR_DEEPSEEK_API_KEY:-}`
从环境注入，不入库）；`POST .../stream` 与历史回放均已在容器内实测（见 §1）。

## 4. CI 状态

- 工作流：`.github/workflows/ci.yml`（backend：postgres+redis service、setup-uv、
  sync → ruff → format → pytest → alembic upgrade/check → openapi 漂移；
  frontend：pnpm install → lint → typecheck → test → 生成类型漂移）。
- main 上 run #2/#3/#4 全绿（M0 与提案阶段）。
- **分支 `m1/chat-milestone` 的 CI 需要 PR 触发**：本机无 GitHub token，PR 需在网页点一下
  （https://github.com/eicon-xyz/better-resume/pull/new/m1/chat-milestone ）。合并进 main 后
  `push: branches: [main]` 也会再跑一次。

## 5. 票据完成情况

| 票 | 内容 | 证据 |
| --- | --- | --- |
| T1 | conversation 持久化 + 事务 seq | 迁移 `b349260daa14`；11 个真库用例（含 20 并发 seq 唯一连续） |
| T2 | 模型注册表 + OpenAICompatAdapter | 迁移 `745c366ba82b`；18 个用例（回放样本、schema 重试/降级、5xx/4xx/超时、脏帧、防火墙） |
| T3 | chat SSE 后端 | 会话 CRUD/历史/stream + 15s 心跳 + 幂等 + 取消落库；12 个用例 |
| T4 | OpenAPI → TS | `scripts/export_openapi.py`、`schema.d.ts`、CI 双侧漂移检查 |
| T5 | api-client | 类型化端点 + POST-SSE + 9 类错误归一；20 个用例 |
| T6 | stream-renderer | 40ms/12 字双通道 + stale 丢弃；6 个用例 |
| T7 | 设计基线 | tokens（浅/深色）+ 6 组件；7 个用例 |
| T8 | 运行态与数据层 | zustand 运行态 + Query 服务端状态 + controller-hook；14 个用例 |
| T9 | chat 页面 | 路由/侧栏/Markdown/打字机/reasoning/历史分页/登录门；6 个用例 |
| T10 | 本文件 | — |

## 6. 与提案的偏差（诚实记录）

1. `Stage` 增加了 `chat`（§12.2 只列了 interview 三阶段）——chat 链路也需要一个 stage 标识。
2. 契约模型重命名：`AuthSessionRequest` / `ChatSessionCreateRequest`（原先两个同名
   `SessionCreateRequest` 让生成的 TS 类型出现命名空间前缀）。
3. 历史接口新增返回 `client_message_id`（前端精确去重所需，原本只能靠内容猜）。
4. reasoning 面板默认展开、由用户折叠（原计划「流式自动展开、完成后自动收起」——
   React 19 的 `set-state-in-effect` 规则下，默认展开更简单且无级联渲染）。
5. 前端新增 `@types/node` + tsconfig `types: ["node", ...]`：干净安装（`--frozen-lockfile`）后
   `vite.config.ts` 里的 `process.env` 才会被类型系统认到——这是「本地干净环境 = CI 环境」暴露的差异。
6. `.env.example` 增加 `BR_SSE_HEARTBEAT_SECONDS`。

## 7. 剩余手动步骤

1. 在网页创建 PR（链接见 §4），让 CI 在分支上跑一次并确认双 job 绿。
2. **轮换 DeepSeek API key**（它曾出现在聊天记录里；`.env` 已被 gitignore，仓库内零命中）。
3. M2 之前无其它待办。
