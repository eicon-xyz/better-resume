# M0 验收证据

> 执行日期：2026-09-13；所有输出均为本机实跑摘录；命令在 `apps/api` 或仓库根执行。

## 0. 环境事实

| 项 | 值 |
| --- | --- |
| OS / 内核 | Ubuntu 22.04.5 LTS（WSL2, 6.6.114.1-microsoft-standard-WSL2） |
| Python | 3.12.14（`uv python install 3.12`；系统 python3 仍是 3.10.12，未使用） |
| uv | 0.12.7（`/root/.local/bin/uv`） |
| node / pnpm | v22.23.2 / 11.20.0 |
| docker / compose | 29.6.2 / v5.3.1 |
| git | 2.55.0（repo-local 身份 `eicon-xyz <eicon-xyz@users.noreply.github.com>`） |

本机沙箱只允许写工作区，因此本地跑 CI 命令需要三个**纯本地**环境变量（CI 不需要，已写入票据）：
`UV_CACHE_DIR=<repo>/.cache/uv`、`DOCKER_CONFIG=<repo>/.docker`、
`npm_config_store_dir|cache_dir|state_dir=<repo>/.cache/pnpm-*`。

## 1. 完成标准逐条

### 1.1 git init + monorepo 结构符合 D08

```
$ git ls-files | wc -l
99
$ git --no-pager log --oneline
<10 条小步提交，message 说 WHAT>
```

结构：`apps/api`（src/better_resume：settings / identity / conversation / llm_gateway /
ai_resilience / interview_engine / resume_parser / media / db / http / observability）、
`apps/web`、`docs`（DECISIONS + 架构分析 + tickets/m0）、`skills/.gitkeep`（占位，内容归 M6）。

### 1.2 docker compose 三服务全部 healthy

```
$ docker compose up -d --wait
 Container better-resume-postgres-1 Healthy
 Container better-resume-redis-1     Healthy
 Container better-resume-api-1       Healthy

$ docker compose ps --format 'table {{.Service}}\t{{.Status}}'
SERVICE    STATUS
api        Up (healthy)    0.0.0.0:8000->8000/tcp
postgres   Up (healthy)    0.0.0.0:5432->5432/tcp
redis      Up (healthy)    6379/tcp            <- 不发布宿主端口（D-C）

$ curl -fsS -i localhost:8000/healthz | head -3
HTTP/1.1 200 OK
x-request-id: 0360494ac7ae4d2daa40ccc2f1004a8b
{"status":"ok"}
```

cookie session 端到端（compose + 真 Redis）：

```
POST /api/v1/auth/session -> 200
  set-cookie: br_session=...; HttpOnly; Max-Age=2592000; Path=/; SameSite=lax
GET  /api/v1/auth/me      -> 200 {"user_id":"compose-user","roles":[]}
docker compose exec redis redis-cli --scan --pattern 'session:*'  -> session:DkuX7F5c...
DELETE /api/v1/auth/session -> 204 ; 之后 /auth/me -> 401 ; 无 cookie -> 401
```

structlog JSON 行带 request_id（含透传）：

```
{"method":"GET","path":"/healthz","status":200,"event":"http_request",
 "request_id":"evidence-123","level":"info","timestamp":"2026-09-13T06:41:45Z"}
```

### 1.3 后端：ruff + pytest + alembic check

```
$ uv run ruff check .            -> All checks passed!
$ uv run ruff format --check .   -> 56 files already formatted
$ uv run pytest                  -> 40 passed
$ uv run alembic upgrade head    -> Running upgrade -> 0001_baseline
$ uv run alembic check           -> No new upgrade operations detected.
$ uv run alembic downgrade base && uv run alembic upgrade head  -> 可逆
```

测试面（只 mock 系统边界）：`/healthz` + request_id 透传/生成/解绑、settings 校验与
`.env.example` 字段契约、identity cookie 属性/滑动过期（假时钟）/fakeredis 往返、
六模块 Protocol 签名与占位实现、Alembic 迁移（真 Postgres，连不上自动 skip）。

### 1.4 前端：eslint + tsc + vitest

```
$ pnpm -C apps/web lint       -> exit 0（eslint 10 + typescript-eslint 8 type-aware）
$ pnpm -C apps/web typecheck  -> exit 0（tsc 6.0.3 --noEmit）
$ pnpm -C apps/web test       -> Test Files 1 passed / Tests 1 passed
$ pnpm -C apps/web build      -> dist/assets/index-*.js 219.83 kB（骨架自检）
```

### 1.5 CI 双 job 就位且语法校验通过

```
$ python3 -c "import yaml...;print(list(d['jobs']))"
jobs: ['backend', 'frontend']   steps: {'backend': 8, 'frontend': 7}
$ python3 -m check_jsonschema --builtin-schema vendor.github-workflows .github/workflows/ci.yml
ok -- validation done
```

action 版本（查证 GitHub releases 后固定）：`actions/checkout@v7`、`astral-sh/setup-uv@v10`、
`pnpm/action-setup@v6`、`actions/setup-node@v7`（node 22）。

### 1.6 六模块包外可导入 + 占位测试

```
$ uv run python -c "import ..."
settings identity conversation llm_gateway ai_resilience interview_engine resume_parser media db
```

`tests/contracts/test_core_contracts.py`（conversation / llm-gateway / ai-resilience）与
`tests/contracts/test_domain_contracts.py`（interview-engine / resume-parser / media）：
逐方法断言 §12.2 的参数名与 async 属性，并断言占位实现被调用时**显式报错**而非静默返回。

## 2. 与票据的偏差（诚实记录）

1. T2 原写「lifespan 初始化 async_sessionmaker」——实际拆到 T5 的 `db` 模块（依赖顺序更干净）。
2. `Stage` 去掉 `demeanor`（D09 砍神态分析，§12.2 注释与 DECISIONS 冲突时以后者为准）。
3. 前端 TypeScript 钉 `^6.0.3`：typescript-eslint 8 尚不支持 TS 7（`does not support TS 7.0`）。
4. `check-jsonschema` 通过清华镜像装到 `.cache/pytools`（pypi 直连偶发 TLS EOF）。
5. `.env.example` 增加 `POSTGRES_*` / `API_PORT`（compose 变量替换需要）。
6. compose 中 redis 不发布宿主端口（本机 6379 被 `dataset-local-redis` 占用）。

## 3. 还需要你做的事

1. 确认本文件与 `OPEN-QUESTIONS.md` 的结论回填。
2. 提供 GitHub remote：已配置 `origin = git@github.com:eicon-xyz/better-resume.git`，
   SSH 认证已验证（`Hi eicon-xyz!`）；GitHub 上该仓库尚未创建（API 404），
   建好空仓库后即可 `git push -u origin main` 并开 PR。
3. 审阅 `docs/resume/M0-resume-draft.md`（D14 硬规则）。

## 4. M0 明确未做（防蔓延）

worker / nginx（D07 的后续里程碑）、interview-report（M2）、skills 知识库（M6）、
任何真实 LLM/ASR/TTS 调用、Redis 分布式单飞 Lua（M6）、JWT、OpenTelemetry、LangChain。
