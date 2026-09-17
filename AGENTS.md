# AGENTS.md

本文件面向人类协作者与 AI 智能体，说明 better-resume 的项目全貌、开发方式与协作规范。

## 项目简介

- **AI 模拟面试平台**（求职作品集项目）：上传简历 → 出题 → 语音/文字答题 → 评分追问 → 报告雷达图 + AI 对话。
- 重写自旧项目 AI-Meeting（Spring Boot），目标是完整度更高、且旧简历的每条亮点在新项目有明确承接物（D01/D16）。
- Monorepo（pnpm workspace）：
  - `apps/api`：Python 3.12 + FastAPI 业务后端（uv 管理依赖）。
  - `apps/web`：React 19 + Vite SPA 前端。
  - `docs/`：决议 / 交接 / 各阶段票据与验收包 / 容量报告。**接手先读 `docs/HANDOFF.md`**。
  - `skills/`：给 AI 的导航——repo-map（"改 X 先看哪"）+ 每个深模块一个 SKILL.md + 生成的 API 索引。
- 决议记录在 `docs/DECISIONS.md`（D01–D17），**与本文冲突时以 DECISIONS.md 为准**。

## 技术栈

- **后端**：Python 3.12 + FastAPI + **SQLAlchemy 2.0 async** + Alembic 迁移（async_sessionmaker 挂 lifespan，全项目统一 `get_session` 依赖）；**structlog**（JSON + request_id，不引 OpenTelemetry）；包管理用 **uv**。
- **数据**：Postgres（关系表 + JSONB，GIN 索引）+ Redis 双件套；不引第三存储（D03）。
- **LLM 编排**：自研轻量——表驱动状态机 + 追问裁决纯函数 + OpenAI 兼容 SDK 直连 + Pydantic response_schema 强校验；**不引 LangChain**（D04）。两层结构：
  - `llm_gateway`：场景绑定（DB 行 + 运行时切换）+ 模型注册（DeepSeek / 百炼 / fake）+ OpenAI 兼容 adapter。
  - `ai_resilience`：单飞 + 熔断 + 舱壁 + 超时 + 进程内限流 token bucket + Redis 分布式单飞；所有供应商调用必须走这条链。
- **语音**：`media` 模块，`TranscriptionChannel`（start/feed/stop/wait → `replace|archive|final` 事件）+ `TtsSynthesizer` 两个缝：
  - ASR：讯飞 AST（流式句池归并 pgs/rg/seg_id）、百炼 Qwen-Audio 批量（`qwen-asr`）、百炼 Paraformer 实时（`paraformer-rt`，边说边出字）。
  - TTS：edge-tts + 缓存。适配器由 `BR_MEDIA__TRANSCRIPTION_ADAPTER` 选择（scripted 为 CI/本地默认）。
- **前端**：React 19 + Vite + TanStack Query + zustand + shadcn/ui；移植旧项目 lib 四件套（request / streamLimiter / audioTranscription / errors）。
- **契约**：后端 FastAPI → `openapi.json` → **openapi-typescript 生成前端类型**（`schema.d.ts`），根治前端猜字段（D17）。
- **实时通道**：转写走 WebSocket（一次性 ticket 握手）、对话走 SSE；认证是 HttpOnly Cookie session（Redis，30 天滑动）+ WS ticket（D11）。
- **测试**：pytest（**只 mock 系统边界**：LLM/时钟/Redis/讯飞/浏览器音频/IPC）+ Vitest；假上游 `apps/api/scripts/fake_openai.py`。
- **部署**：单机 docker compose——nginx（宿主 :8080，唯一入口）+ api×N（`--scale`）+ worker（Redis Stream 任务）+ postgres + redis + 一次性 migrate 服务（D07）。无 K8s。
- **CI**：GitHub Actions 双 job——backend（ruff + pytest + alembic check）/ frontend（eslint + tsc + vitest）。

## 环境准备（本机陷阱，踩过的别再踩）

- `uv` 在 `~/.local/bin`：新 shell 先 `export PATH="$HOME/.local/bin:$PATH"`。
- pytest **必须显式导出测试库地址**，否则依赖 DB 的用例会 skipped（不是失败）：

  ```bash
  cd apps/api
  export BR_DATABASE_URL='postgresql+asyncpg://better_resume:better_resume@127.0.0.1:5433/better_resume'
  export BR_REDIS_URL='redis://127.0.0.1:6379/0'
  ```

  端口：**原生测试库 Postgres 5433 / Redis 6379；compose 内网 postgres 5432（不发布）、nginx 宿主 8080**。
- pytest 输出被 `-q` 压掉摘要：**一律 `--junitxml` 读数，且先 rm 旧 xml**（否则读到陈旧结果）。
- Docker 构建：`build.network: host` + shell 带 `HTTPS_PROXY=http://127.0.0.1:7897`；`.env` 里有镜像站前缀（Docker Hub 直连不通）；**不要**往 `~/.docker/config.json` 写 proxies。
- 本机**没有 ffmpeg**：转音频用 `uv run --with soundfile --with numpy python …`。
- 本机 `NO_PROXY` 含裸 IPv6：新建 httpx/ws 客户端一律显式兜底（`trust_env=False` / `proxy=None`，P20/P24）。
- GitHub 走 SSH；`gh` API 偶发 SSL EOF——命令前带代理变量 `export HTTPS_PROXY=http://127.0.0.1:7897 HTTP_PROXY=…`，失败重试。
  - **该代理（7897）不一定在跑**：没起时直连 HTTPS 被本机 Watt Toolkit 的中间人证书（CN=SteamTools Certificate）拦截，
    系统 CA 不认 → `gh` **误报「token invalid」**。修法：`openssl s_client -connect api.github.com:443 -servername
    api.github.com -showcerts </dev/null | awk '/BEGIN CERT/,/END CERT/' > /tmp/chain.pem`，再 `export SSL_CERT_FILE=/tmp/chain.pem`
    （`git push` 走 ssh.github.com:443，不受影响）。
- **改过 volume 挂载的文件（如 `deploy/nginx.conf`）后 `restart` 会失败**（WSL2 bind-mount inode 失效："no such file or directory"）→ 用 `docker compose up -d --force-recreate <svc>` 重新挂载，不要重启引擎。
- **出网 22 端口可能被拒**：`git push` 报「检查权限/仓库存在」时先 `ssh -T git@github.com`；被拒就走 443：`git push ssh://git@ssh.github.com:443/<owner>/<repo>.git <branch>`。
- **Docker Desktop 的 WSL 集成会掉线**（症状：`docker` 命令突然消失，`/mnt/wsl/docker-desktop` 挂载没了）：用
  `powershell.exe -NoProfile -Command Start-Process 'C:/Program Files/Docker/Docker/Docker Desktop.exe'` 拉起，
  等约 1 分钟后 `docker compose up -d --wait --scale api=2`（2026-09 实际踩过一次）。
- 真机凭据**只进仓库根 gitignored `.env`**；`.env.example` 只写变量名。目前有 `BR_DEEPSEEK_API_KEY`、`BR_DASHSCOPE_API_KEY`（LLM+ASR 共用）、`BR_ARK_API_KEY`（弃用）。

## 常用命令

```bash
# 单一入口（CI 与本地跑同一份命令，P2-T1）——先 --list 看全层
bash scripts/verify.sh --list
bash scripts/verify.sh --layer all            # 本地收口：unit+contract+scripts
bash scripts/verify.sh --layer real --dry-run # 真机清单+预算（不花钱）

# 后端全量测试（778 例；不导出 BR_* 会静默 skip）
cd apps/api && uv run pytest -q --junitxml=/tmp/x.xml

# 前端测试（175 例）——必须从仓库根跑
cd '/root/better resume' && pnpm -C apps/web test --run

# 契约三件套：改过 REST 模型后必须一起跑（漏一步 = 本地绿 CI 红，M6 P16）
cd apps/api && uv run python scripts/export_openapi.py
pnpm -C apps/web gen:api
uv run python scripts/extract_api_index.py --check

# compose 栈（nginx :8080 唯一入口；改前端后必须 --build nginx 才上新 bundle）
export BR_SMOKE_KEY=smoke-fake-key BR_SSE_HEARTBEAT_SECONDS=1
docker compose up -d --build --wait --scale api=2
docker compose --profile smoke down -v   # 停栈

# 验收脚本（会自己起栈）
bash scripts/compose_smoke.sh            # 部署面：REST/SSE/WS/非 root/双实例轮询/worker 心跳
bash scripts/kill_instance_drill.sh      # kill 正在服务的实例，状态/报告一致
bash scripts/fault_injection_drill.sh    # 5 个故障实验 + 浸泡（--quick 2 分钟浸泡）

# P1-D 生产形态演练（恢复动作在 finally，可安全重跑；各约 1 分钟）
uv run python -m scripts.fault_probe fault --scenario redis-partition --seconds 20
uv run python -m scripts.fault_probe fault --scenario redis-failover  --seconds 20
# P1 真机探针（各 1 次真调用）
uv run python scripts/assembler_real_probe.py        # 真机增量包回放句池（提交语义 + 已知边界）

# 真机冒烟（需 .env 凭据；不属于 CI）
uv run python -m scripts.real_model_smoke            # 四条 LLM 链路 + 失败面
uv run python scripts/media_smoke.py --paraformer-rt-real --wav ../../data/audio/v3-sample-16k.wav   # 实时 ASR
uv run python scripts/media_smoke.py --qwen-asr-real --wav ../../data/audio/v3-sample-16k.wav        # 批量 ASR
uv run python scripts/v3_ws_probe.py --realtime      # 端到端（穿 nginx）：增量帧时序 + 关闭码
```

## 代码结构

```text
├── apps/api/                        # FastAPI 后端（uv 工程）
│   ├── src/better_resume/
│   │   ├── settings/config.py       # 全部设置（BR_ 前缀；凭据字段空默认；嵌套用 BR_MEDIA__XX）
│   │   ├── main.py                  # lifespan 装配
│   │   ├── http/                    # REST/WS/SSE 端点；media.py 是转写 WS（票据→音频→事件→关闭码）
│   │   ├── identity/                # Cookie session（Redis）+ WS ticket；后端不可用=503（P17）
│   │   ├── db/                      # SQLAlchemy async 引擎/session/migrations
│   │   ├── llm_gateway/             # 场景绑定 resolver + 模型注册 + adapters（openai_compat/星云）
│   │   ├── ai_resilience/           # 单飞/熔断/舱壁/超时/限流/分布式单飞（假时钟可测）
│   │   ├── interview_engine/        # 题级锁/热层/报告冻结
│   │   ├── conversation/ + chat/    # chat + interview 两类会话（D09）
│   │   ├── resume_parser/           # pdfplumber + 章节启发式（解析不靠 LLM，D10）
│   │   ├── media/                   # 转写/TTS 缝 + assembler 句池归并 + adapters/（xunfei_ast、qwen_asr、paraformer_rt、edge_tts、scripted）
│   │   ├── jobs/ + worker.py        # Redis Stream 队列 + worker（心跳/重试/死信/接管）
│   │   └── observability/           # structlog 配置
│   ├── migrations/                  # Alembic
│   ├── scripts/                     # real_model_smoke / fault_probe / load_test / media_smoke / v3_ws_probe / assembler_real_probe / fake_openai / export_openapi / extract_api_index
│   ├── tests/                       # pytest（hermetic；test_source_hygiene 拦语法警告）
│   └── openapi.json                 # export_openapi.py 产物（契约源，勿手改）
├── apps/web/                        # React 19 + Vite SPA
│   ├── src/api/                     # 请求层：client/errors/sse + schema.d.ts（生成，勿手改）
│   ├── src/audio/                   # capture/pcm/player/transcriptStore/transcriptionSocket
│   ├── src/pages/ + scenes/         # 页面（面试间/聊天/报告/设置）与查询
│   └── src/stream/                  # SSE 渲染
├── docs/                            # HANDOFF.md、DECISIONS.md、tickets/（m0..m6、v1-verification、p1-post-v）、perf/
├── skills/                          # repo-map + modules/<模块>/SKILL.md + api-index（生成）
├── scripts/                         # compose_smoke.sh / kill_instance_drill.sh / fault_injection_drill.sh
├── deploy/nginx.conf                # upstream 变量 + resolver（--scale 生效的关键，M6 P12）
├── compose.yaml                     # 部署最终形态（api/worker/postgres/redis/nginx/migrate/fake-llm）
└── .env.example                     # 变量名清单（真凭据只进 gitignored .env）
```

## 核心协作模式：阶段提案制 + 契约三件套

**流程（用户明确要求，永久生效）**：

1. **先提案**：新阶段写 `docs/tickets/<stage>/README.md`（范围/不做/交付物/测试与验收口径/预估/需要用户决定的问题），**等用户确认后才动工**。
2. **红-绿 TDD 执行**：先写失败测试再实现；小步提交，提交信息说 WHAT。
3. **交验收包**：`ACCEPTANCE.md` / `EVIDENCE.md`——可复跑命令 + 原始输出 + 数字 + **未验证项（诚实清单）** + 与提案的偏差。
4. **由用户验收**：AI 不自行宣布完成、**不擅自合并 PR / 删分支**；难题即时记 `PROBLEMS.md`。

**契约三件套（改过 REST 模型后必须一起跑）**：`export_openapi.py` → `pnpm -C apps/web gen:api` → `extract_api_index.py --check`。漏一步的症状是"本地全绿、CI 直接红"（M6 P16）。

## 开发规范

- 语言与沟通：全部使用简体中文（注释、文档、对话）；提交信息用英文短句说 WHAT（沿用现有风格，如 `fix(media): …(P1-A)`）。
- **只 mock 系统边界**（LLM/时钟/Redis/讯飞/浏览器音频/IPC），不 mock 内部模块；测试必须 hermetic（P15）——断言不依赖 shell 里的代理变量/PATH/DB 地址。
- **TDD 循环纪律**（P1-A 复盘，2026-09-15）：测试只写在事先向用户确认的缝上；**垂直切片**——一个用例红 → 最小实现绿 → 下一个，不整批铺测试（整批的代价：P1-A 绿灯期连修 3 个测试自身 bug）；任何行为变更（含验证期热修）先在旧代码上演示红再改；断言走公开行为或 fake 协作对象的入参捕获，不加测试专用属性。
- **所有供应商调用走 `ai_resilience` 链**（Stage 分类），不要裸调；时间用注入时钟测，不写真实 sleep 断言。
- **错误语义**：依赖不可用/缺配置 → **503 + Retry-After** 并点名缺失变量（P17），不是 401 也不是 500；响应要能区分"你没登录"和"我这边坏了"。
- **缓存**：跨进程可见的配置缓存必须带 TTL 或写路径失效（P18——多副本下"只在本地失效"= 配置漂移）。
- **WS 转写**：成功路径显式 `close(1000)`（P21，否则客户端报 1006）；失败关 4411；前端转写文本**追加、同段去重、绝不覆盖手写**（P23）。
- **WS/HTTP 客户端连接参数一律显式**：`open_timeout`、`close_timeout`（供应商会拖关闭握手，默认 10s 会让松手→final 变 10 秒，P24）、`proxy=None` 或 `trust_env=False` 兜底（P20）。
- **证据诚实**：真模型响应必带 `usage`（流式需按模型行 `extra.stream_usage=true` 请求，P19）；fake 上游（`smoke-fake`）无 usage——不许拿假的冒充真的；未验证就写未验证。
- **依赖纪律**：不引入 LangChain / OpenTelemetry / 请求层重试库等被决议排除的依赖（D04/D17）；新增依赖先在提案里说明。
- 设置新增走 `settings/config.py`（`BR_` 前缀；嵌套用 `__`）；compose 需要透传的新变量同步加到 `compose.yaml` 与 `.env.example`（只写变量名）。
- 部署形态变更（compose/nginx）必须同步更新对应验收脚本并在票据里留证据；nginx upstream 用变量 + resolver，否则 `--scale` 不生效（M6 P12）。
- 清洁度：不留临时文件、注释掉的死代码、"默认关闭没人跑"的分支——要么真机跑通并设为默认，要么删掉。

## 贡献指南（提交前检查清单）

- `uv run ruff format && uv run ruff check`（apps/api 下）；改了 Python 必跑后端全量 pytest（带 BR_* env、junitxml 读数）。
- 改了前端必跑 `pnpm -C apps/web test --run` + eslint + tsc；改了 REST 模型必跑**契约三件套**。
- 动了部署面（compose/nginx/worker）跑 `bash scripts/compose_smoke.sh`；动了韧性/分布式跑 `kill_instance_drill.sh`。
- 新阶段/票据/验收包放 `docs/tickets/<stage>/`；`docs/HANDOFF.md` 在阶段收口时同步更新；`skills/` 索引用生成脚本刷新，不手改。
- 真机凭据只进 `.env`；任何密钥/令牌不得出现在代码、测试、票据、日志摘录里。

## AI 智能体须知（关键上下文）

- **开工顺序**：先读 `docs/HANDOFF.md`（状态/怎么跑/坑），再按 `skills/repo-map/SKILL.md` 路由到对应模块的 `SKILL.md`；跨窗口断点在 `~/.dsh/session-memory/better resume.md`（仓库外）。
- **版本差异**：Python 3.12（`asyncio.TimeoutError` 即 `TimeoutError`）；websockets ≥14 把 `extra_headers` 改名 `additional_headers` 且新增 `proxy` 参数——写适配器要兼容两种签名（见 `media/adapters/paraformer_rt.py:open_connection` 的写法）。
- **供应商语义**：百炼批量 ASR（qwen-audio-3.0-asr-flash）= 整段一次返回；实时（paraformer-realtime-v2）= WS 增量，`result-generated.sentence.sentence_end` 区分 live/完结；二者共用同一 workspace 域名与 key。
- **worker/Redis**：队列兼容 Redis 6.0 下限（无 `XAUTOCLAIM`，M6 P7）；worker 不允许死于依赖抖动——
  **循环里每一次依赖调用（含心跳写）都必须在兜底 try 内**（P26：心跳写在 try 外，主从切换时 worker exit 1）；
  崩溃恢复时间 ≈ 接管阈值本身，不要美化数字。
- **e2e 探针会撒谎**：探针"发完才收"会把服务器帧的到达时序塌缩（P25）；探针漏了前置状态（如 cookie）会把 503 读成 401（P27）——
  证据工具必须先于结论被校准；演练的故障恢复动作必须放 `finally`；所有数字写清口径（探针超时会截断"接管耗时"这类测量，V6 教训）。
- **前端转写合并历史上存在三层**（store 事件 → 页面 onTranscript → chat Composer 内部 prop effect，P28/P30 各漏过一层）：
  改任何合并语义前必须 `grep` 全部调用点清零，且测试要覆盖「prop 逐事件驱动组件内部合并」这条路径（store 级测试测不到它）。
- **部署面：index.html 必须 `Cache-Control: no-store`、`/assets/` `public, immutable`**（P29：不发头=浏览器启发式缓存 HTML，部署后还在跑旧 bundle；compose_smoke 有断言）。改前端后要 `up -d --build nginx` 并核对新 hash。
- 本文件（AGENTS.md）是长期协作文档：技术栈、命令、约定有变化时应同步更新；与 `docs/DECISIONS.md` 冲突时以后者为准。
