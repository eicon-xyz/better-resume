# T15 证据：部署与连接默认值单一声明

## 意图复述

- 我理解这票解决什么：P02 那类「部署面与浏览器边界的隐式默认值只有真跑该形态才暴露」的坑——缓存头与非 root 两条断言散在 `scripts/compose_smoke.sh` 里，迁移步骤、upstream 解析、WS 超时只有真机踩过才暴露；票要把每条隐式默认值收成一份声明（缓存头 / 迁移步骤 / 非 root / upstream 解析 / WS 超时），每条默认值都配一条真跑该形态、会变红的断言。
- 我怎么做，到文件粒度：新增 `scripts/deploy_defaults.sh` 作唯一真源（每条默认值 = 它写在哪个文件 + 声明位锚点 + 真跑时要读到的期望值），改造 `scripts/compose_smoke.sh` 按 id 读声明并真跑判定（响应头、一次性迁移作业、容器 uid、`--scale` 后的实例数、运行中 nginx 的 `nginx -T`）。
- 我不做什么：不改 `compose.yaml` / `deploy/nginx.conf`（它们是被声明描述的对象）、不碰 `verify.sh`、不引依赖、不动 p14 在飞改动与 p15 以外的文档；不 commit / push / 开 PR。

## 交付物与消费关系

- 新增 `scripts/deploy_defaults.sh`：唯一真源。每条默认值一行，`BR_DEPLOY_DEFAULTS[<id>]='<surface>|<anchor>|<k=v;k=v>'`——描述文件、声明位锚点、真跑时要读到的期望值都在这一行里。
- 改造 `scripts/compose_smoke.sh`：source 声明文件，按 id 读期望值并真跑该形态；脚本里没有第二份数值（检查标签只印 id，实测读数由判定函数打印）。
- 声明里清空任一字段、把断言值改错、或整条记录删掉，对应的那条检查立刻转红（红演示 A/B/C 见下）。
- 写入面：本票只写 `scripts/compose_smoke.sh`（改）与 `scripts/deploy_defaults.sh`（新增），外加票面要求的两段证据；`compose.yaml` / `deploy/nginx.conf` / `verify.sh` 零改动（`git diff` 里 `scripts/verify.sh` 的改动属 T8 在飞，不是本票）。

| 默认值 id | 声明位（文件：锚点） | 真跑该形态的判定 | 本轮实测读数 |
| --- | --- | --- | --- |
| `spa-cache-headers` | `deploy/nginx.conf`：`add_header Cache-Control` | `GET /` 与 hashed asset 的 `Cache-Control` == 声明值 | `/` → `no-store`；`assets/index-ByEg2Orj.js` → `public, immutable` |
| `one-shot-migrate` | `compose.yaml`：`command: ["alembic", "upgrade", "head"]` | 一次性迁移作业真跑 `alembic current`，schema 停在 head | `b8e1f4c2d9a3 (head)` |
| `containers-non-root` | `apps/api/Dockerfile`：`USER app` | api / worker 容器里的 `id -u` != 声明的 `forbidden_uid` | api uid=999、worker uid=999（禁止 0） |
| `dynamic-upstream` | `deploy/nginx.conf`：`resolver 127.0.0.11 valid=10s ipv6=off` | `--scale api=2` 后采样，`X-Instance-Id` 去重数 >= `min_instances` | 采样 12 次命中 2 个（声明 >= 2） |
| `ws-idle-timeout` | `deploy/nginx.conf`：`proxy_read_timeout 300s` | 运行中 nginx 的 `nginx -T` 里带着声明的指令与秒数 | `proxy_read_timeout 300s;` |

## 红-绿

### 绿：真跑栈（原样可复跑）

```bash
cd '/root/better resume'
export PATH="$HOME/.local/bin:$PATH"
export UV_CACHE_DIR='/root/better resume/.cache/uv'
# 本机 compose v5.6.0 已无 COMPOSE_BAKE 开关、构建闸门拒 `network: host`（见「环境事实」节），
# 因此覆写 build.network；被断言的运行形态与 compose.yaml 完全一致。
export COMPOSE_FILE='/root/better resume/compose.yaml:/tmp/t15-buildoverride.yaml'
bash scripts/compose_smoke.sh
```

原始输出（完整 562 行日志在 /tmp/t15-run-green.log；下面是声明相关的五段与收尾，容器编排行按原样保留）：

```text
== declared default: one-shot-migrate
  声明位 compose.yaml: command: ["alembic", "upgrade", "head"]
   Container better-resume-postgres-1 Running 
   Container better-resume-postgres-1 Waiting 
   Container better-resume-postgres-1 Healthy 
   Container better-resume-migrate-run-0eebc4b1e5b4 Creating 
   Container better-resume-migrate-run-0eebc4b1e5b4 Created 
  INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
  INFO  [alembic.runtime.migration] Will assume transactional DDL.
  b8e1f4c2d9a3 (head)
PASS: the one-shot migrate job leaves the schema at head
```

```text
== SPA is served by nginx
PASS: GET / returns the built SPA

== declared default: spa-cache-headers
  声明位 deploy/nginx.conf: add_header Cache-Control
  GET / -> Cache-Control: no-store（声明 no-store）
  GET assets/index-ByEg2Orj.js -> Cache-Control: max-age=31536000
Cache-Control: public, immutable（声明 immutable）
PASS: SPA and hashed assets carry the declared Cache-Control

== declared default: containers-non-root
  声明位 apps/api/Dockerfile: USER app
  api uid=999（禁止 0）
  worker uid=999（禁止 0）
PASS: api/worker run as the declared non-root uid
```

```text
== REST through nginx (session cookie + model registry)
healthz: 200 instance=004dcfe8c9ef
models: ['deepseek-flash', 'deepseek-v4-pro', 'smoke-fake']
smoke-fake: {"name": "smoke-fake", "model_id": "smoke-fake", "provider": "openai_compat", "supports_reasoning": false, "configured": true, "is_default": false}
REST PASS
PASS: REST probe

== SSE through nginx (heartbeat + fake vendor chunks, not buffered)
stream: 200 content-type=text/event-stream; charset=utf-8
  [  1.08s] : ping
  [  2.08s] : ping
  [  2.10s] event: content
  [  2.10s] data: {"text": "今天"}
  [  2.30s] event: content
  [  2.30s] data: {"text": "天气"}
  [  2.50s] event: content
  [  2.50s] data: {"text": "不错。"}
  [  2.50s] event: done
  [  2.50s] data: {"finish_reason": "stop"}
frames=10 content=3 heartbeats=2 first_frame_at=1.08s stream_span=1.42s
SSE PASS
PASS: SSE probe

== WebSocket upgrade through nginx (/api/v1/media/transcribe)
WS_OPEN ws://127.0.0.1:8080/api/v1/media/transcribe
WS first frame: (none within 3s, handshake only)
WS PASS
PASS: WS probe

== declared default: ws-idle-timeout
  声明位 deploy/nginx.conf: proxy_read_timeout 300s
  运行中的 nginx:         proxy_read_timeout 300s;
PASS: the running nginx carries the declared read timeout
```

```text
== declared default: dynamic-upstream
  声明位 deploy/nginx.conf: resolver 127.0.0.11 valid=10s ipv6=off
  （扩容期间 40 余行容器状态行按原样留在 /tmp/t15-run-green.log，此处省略）
  采样 12 次，X-Instance-Id 命中 2 个（声明 >= 2）: 004dcfe8c9ef b4ac71cb9af3
PASS: nginx reached at least the declared number of api instances
```

```text
== summary
ALL CHECKS PASSED (edge: http://127.0.0.1:8080; stop with: docker compose --profile smoke down -v)
EXIT=0
```

### 红 A：声明里清空一条默认值的断言 → 该条检查必红

复跑方式（跑完还原；A 只删掉 `spa-cache-headers` 的期望值字段）：

```bash
cd '/root/better resume'
cp scripts/deploy_defaults.sh /tmp/t15-decl-backup.sh
sed -i 's|index_path=/;index_header=no-store;asset_header=immutable|index_path=/|' scripts/deploy_defaults.sh
bash scripts/compose_smoke.sh; echo "exit=$?"   # 期望：非 0，且该条 FAIL
cp /tmp/t15-decl-backup.sh scripts/deploy_defaults.sh
```

原始输出（红 A 日志 /tmp/t15-red-A.log，exit=1）：

```text
== SPA is served by nginx
PASS: GET / returns the built SPA

== declared default: spa-cache-headers
  声明位 deploy/nginx.conf: add_header Cache-Control
默认值 spa-cache-headers 的声明里缺少 index_header
FAIL: SPA and hashed assets carry the declared Cache-Control
```

```text
== summary
SOME CHECKS FAILED (see above)
```

### 红 B：把断言值改错 → 真跑读数与声明不符必红（断言读的是运行形态，不是文件字面量）

```bash
sed -i 's|min_instances=2|min_instances=3|' scripts/deploy_defaults.sh
bash scripts/compose_smoke.sh; echo "exit=$?"   # 期望：非 0，只有 2 个副本而声明要 3 个
```

原始输出（红 B 日志 /tmp/t15-red-B.log，exit=1）：

```text
== declared default: dynamic-upstream
  采样 12 次，X-Instance-Id 命中 2 个（声明 >= 3）: 2bd46f278f41 75a2b8c795d0
FAIL: nginx reached at least the declared number of api instances
```

```text
== summary
SOME CHECKS FAILED (see above)
```

### 红 C：整条记录删掉 → 「声明里没有该 id」必红（P15-3 那类「接线删掉仍绿」）

```bash
sed -i '/\[containers-non-root\]=/d' scripts/deploy_defaults.sh
bash scripts/compose_smoke.sh; echo "exit=$?"   # 期望：非 0，声明里没有这个 id
```

原始输出（红 C 日志 /tmp/t15-red-C.log，exit=1）：

```text
== declared default: containers-non-root
声明里没有默认值 containers-non-root（scripts/deploy_defaults.sh）
FAIL: api/worker run as the declared non-root uid
```

```text
== summary
SOME CHECKS FAILED (see above)
```

### 还原与复跑

```text
原声明 sha256=cfbeb907becfc0ad4a1d2bac69217d269858ca3319a46a86d7cb9ad397433b8f
还原后复跑绿基线 exit=0
还原后 sha256=cfbeb907becfc0ad4a1d2bac69217d269858ca3319a46a86d7cb9ad397433b8f
sha256 逐字节一致
```

还原复跑的原始尾行（/tmp/t15-restored-green.log）：

```text
== summary
ALL CHECKS PASSED (edge: http://127.0.0.1:8080; stop with: docker compose --profile smoke down -v)
```

## 本机环境事实：compose 已无 COMPOSE_BAKE，构建闸门挡住三个演练脚本

不覆写构建网络时，`bash scripts/compose_smoke.sh` 在本机必然停在第一步构建（与票面验收口径 3 的「栈不在就先按 docs/HANDOFF.md §3 起栈并注明」相互印证）：

```text

== compose config is valid
PASS: docker compose config

== postgres + redis, then seed the smoke-fake model row
 Container better-resume-postgres-1 Running 
 Container better-resume-redis-1 Running 
 Container better-resume-postgres-1 Waiting 
 Container better-resume-redis-1 Waiting 
 Container better-resume-postgres-1 Healthy 
 Container better-resume-redis-1 Healthy 
 Container better-resume-postgres-1 Running 
 Image better-resume-api Building 
#1 [internal] load local bake definitions
#1 reading from stdin 704B done
#1 DONE 0.0s
additional privileges requested: pass "--allow=network.host" to grant requested privileges
```

根因是可复现的环境事实，不是本票改动：

```bash
$ docker compose version
Docker Compose version v5.6.0
$ docker buildx version
github.com/docker/buildx v0.37.2 2d379c0c3f22da0d2759d132a0ec81ca949098f0
$ strings /usr/local/lib/docker/cli-plugins/docker-compose | grep -c COMPOSE_BAKE
0
$ git diff -- scripts/compose_smoke.sh | grep -c 'run --rm --build migrate'
0
$ git show HEAD:scripts/compose_smoke.sh | grep -n 'build migrate'
109:docker compose run --rm --build migrate
```

- P45 的出口是 `export COMPOSE_BAKE=false`（classic 路径把 entitlements 交给 builder）；本机 compose **v5.6.0 的二进制里 `COMPOSE_BAKE` 零命中**，该出口已不存在，`--build` 恒走 bake，而 `compose.yaml` 的 `network: host` 请求的权限 Compose 从不授予 → `additional privileges requested: pass "--allow=network.host"`。
- 失败的 `docker compose run --rm --build migrate` 是 HEAD 里第 109 行的原有命令，本票未改（`git diff` 计数 0）。三个构建栈的脚本同受影响。
- 本轮取真跑读数用的覆写（只改**构建期**网络，运行形态与 `compose.yaml` 完全一致；覆写文件在 /tmp，不在仓库内）：

```yaml
services:
  migrate: { build: { network: default } }
  api: { build: { network: default } }
  worker: { build: { network: default } }
  fake-llm: { build: { network: default } }
  nginx: { build: { network: default } }
```

## 验收命令与原始输出

### 1. `bash scripts/compose_smoke.sh` → ALL CHECKS PASSED（exit=0）

命令见「绿」节（含 `COMPOSE_FILE` 覆写与三件套 export）。读数：`exit=0`、`ALL CHECKS PASSED (edge: http://127.0.0.1:8080; stop with: docker compose --profile smoke down -v)`；五条声明检查全 PASS，原始输出已在上面逐段贴出。

### 2. `bash scripts/verify.sh --layer scripts` → ALL PASS (12 commands)（exit=0）

```bash
cd '/root/better resume'
export PATH="$HOME/.local/bin:$PATH"
export UV_CACHE_DIR='/root/better resume/.cache/uv'
export BR_DATABASE_URL='postgresql+asyncpg://better_resume:better_resume@127.0.0.1:5433/better_resume'
export BR_REDIS_URL='redis://127.0.0.1:6379/0'
bash scripts/verify.sh --layer scripts
```

```text
[1/12] bash scripts/verify_secrets.sh --selftest
[2/12] bash scripts/verify_secrets.sh
[3/12] bash scripts/verify_docs_hygiene.sh --selftest
[4/12] bash scripts/verify_docs_hygiene.sh
扫描 511 个文件，命中 0 处；豁免 5 处命中（脚本内清单）。
[5/12] bash scripts/verify_citations.sh --selftest
[6/12] find docs/tickets -name '*.md' ! -name '*-EVIDENCE.md' -print0 | xargs -0 bash scripts/verify_citations.sh
引证 104（直配 69，短名兜底 35）解析成功 104 失败 0
[7/12] bash scripts/ticket_frontier.sh --selftest
[8/12] bash scripts/ticket_frontier.sh --check docs/tickets/p15-agent-friendly-architecture
OK docs/tickets/p15-agent-friendly-architecture：结构校验通过（18 张票）
[9/12] cd apps/api && uv run pytest tests/test_fault_probe.py tests/test_drill_prereqs.py tests/test_load_test_script.py tests/test_real_model_smoke_script.py tests/test_verify_script.py tests/test_web_style_guards.py
101 passed, 2 warnings in 6.70s
[10/12] for f in scripts/*.sh; do bash -n "$f" || exit 1; done; echo 'shell syntax ok'
shell syntax ok
[11/12] uv run --project apps/api python scripts/check_scripts.py
script syntax ok (24 python scripts, SyntaxWarning treated as an error)
[12/12] uv run --project apps/api python scripts/verify_audit_evidence.py --structural
structure ok: 10 units / 122 issues / 341 citations
ALL PASS (12 commands) -- evidence: var/evidence/20261017T051812Z-scripts
EXIT=0
```

（原始输出完整 77 行；上面按行首过滤，只摘掉自检的逐条明细。）

## 实现决定交代

| spec 未覆盖、我自行拍定的决定 | 为什么这么拍 | 我明确没做的 |
| --- | --- | --- |
| 声明用 bash 关联数组（`id → surface / anchor / k=v…`），断言代码留在消费方 `compose_smoke.sh` | 声明文件是**期望值**的唯一真源；判定机制（curl / docker exec / compose run / nginx -T）是消费方的职责，一套机制服务五条默认值，声明里不塞 shell 片段（避免 eval） | 没做 JSON/YAML 声明（要引 jq/yq 或自写解析器，多一份依赖与解析面） |
| 五条检查沿用原本的位置与顺序：缓存头与非 root 在原处，迁移检查跟在 `up --wait` 之后，WS 超时跟在 WS 探针后，upstream 检查替换原来的 `--scale` 段 | 不改变既有证据的含义（REST/SSE/WS 三条探针仍跑在单副本上），每条断言落在它描述的那一步 | 没把五条合成一个「默认值总检」步骤（会改掉既有探针的副本身份语义） |
| `--scale api=2` 的字面量留在 `compose_smoke.sh`，断言侧的数字 `min_instances` 来自声明 | `apps/api/tests/test_deploy_manifest.py` 用子串把这条场景钉在文档形态上，该测试不在本票写入路径内；把场景数字也搬进声明会把它打红。断言值仍只有声明一份 | 没改那条测试，也没把 `--scale` 的取值改成读声明（与既有测试直接冲突） |
| 迁移判定用 `docker compose run --rm -T <service> <exec>` 真跑一次一次性作业，判据是输出里的 `(head)` | 「迁移步骤存在」只有真跑该形态才算证据；`(head)` 是可数的值 | 没拿 compose 的 `depends_on` 字符串当判据（静态形状已由 `docker compose config` 覆盖） |
| WS 超时的判据取运行中容器的 `nginx -T` 有效配置里的指令与秒数 | 等真实的 60s 超时会让冒烟挂满分钟级；`nginx -T` 读的是运行中实例展开后的配置，指令缺失即红 | 没做「连接活过 300s」的长连断言（时间成本换不到更多信息）——列入未验证项 |
| 五条检查改走 `judge <label> <判定函数>`（判定失败不触发 `set -e` 提前退出） | 旧写法（裸管线 + `check $?`）在第一条红处直接退出，FAIL 行与摘要都打不出来；红演示要求「一条红、其余继续、最后非 0」 | 没重排其余既有检查的写法（本票只动这五条） |
| 本机取读数时用 `COMPOSE_FILE=compose.yaml:/tmp/t15-buildoverride.yaml` 覆写 `build.network: default` | 只改构建期网络（缓存热，构建不需要网），不改任何被断言的运行形态；构建闸门是本机 compose v5.6.0 的环境事实 | 没改三个演练脚本的构建行为、没改 `compose.yaml`（红线）、没把覆写文件放进仓库 |

## 未验证项

- **未在本机取得「不覆写 `build.network`」的全绿**：compose v5.6.0 的二进制已无 `COMPOSE_BAKE` 开关，`--build` 恒被 buildx 0.37.2 的同意闸门拒（`additional privileges requested: pass "--allow=network.host"`）。这是环境事实（三个构建栈的脚本同受影响），本票未改那条命令；本轮绿读数是在覆写构建网络下取得的。
- **WS 空闲超时只验到运行配置**：`nginx -T` 里带着 `proxy_read_timeout 300s`，没验「一条空闲连接真的活过 300s（或被 60s 切掉）」。
- **upstream 只验到扩容方向**：扩容到 2 个副本后 nginx 轮询到 2 个实例；没验 `resolver valid=10s` 到期后的重新解析与副本下线（缩容 / 重建容器）场景。
- **未跑 `--layer all` 与后端全量 pytest**：本票只改 `scripts/` 与票据证据；全量读数按派活口径由出票方串行复跑（并行期共享库读数不可信，见 PROBLEMS P15-1）。
- **未跑 `kill_instance_drill.sh` / `fault_injection_drill.sh`**：本票未改它们的输入；它们与本脚本同受本机构建闸门影响，本轮未验。
- **「代理」这条隐式默认值未纳入声明**：README 建议 4 提到代理，票面验收口径的五条里没有；vite 开发代理（`apps/web/vite.config.ts`）不在 compose 冒烟的运行形态里，配不出「真跑该形态」的断言。
