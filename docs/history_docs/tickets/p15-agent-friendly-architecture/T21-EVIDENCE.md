# T21 构建闸门出口适配 compose v5 — 证据

## 意图复述

- 目标：compose v5.6.0 + buildx 0.37.2 下 P45 的 `COMPOSE_BAKE=false` 出口已失效（二进制里零命中），三个构建栈脚本的 `--build` 被 bake 同意闸门拒；本票要恢复构建出口，让 `compose_smoke.sh` 与至少一个 drill 的构建步在本机 exit 0，且不再需要 /tmp 覆写。
- 方法：先真跑两个候选原型（构建参数授权 vs `build.network` 改 default），各自记录网络可达性（代理/镜像站）与耗时，用读数定方向；结论只落到 `scripts/` 的构建调用行（必要时 `compose.yaml` 的 build.network）。
- 红线：不改部署运行形态（网络/端口/副本数）、不动 `deploy/nginx.conf`、不引依赖、不 commit/push/开 PR；授权必须显式且注释 why，不放宽闸门，不把本机绕过写进脚本。

## 原型读数（两个候选各真跑）

### 本机事实

```text
$ docker compose version
Docker Compose version v5.6.0
$ docker buildx version
github.com/docker/buildx v0.37.2 2d379c0c3f22da0d2759d132a0ec81ca949098f0
$ docker version --format "{{.Client.Version}} / {{.Server.Version}}"
29.8.2 / 29.8.2
```

- `docker compose build --help` 只有 `--print`，**没有** `--allow`；`docker compose` v5.6.0 二进制里 `COMPOSE_BAKE` 零命中（与 T15-EVIDENCE 的环境事实一致）。
- `docker compose build --print` 的输出才是可用的 bake 文件：五个服务都带 `tags` 与 `output: [type=docker]`（nginx 是 `better-resume-nginx`）。`docker buildx bake -f compose.yaml` 直读也行，但 nginx 拿不到 tag、也不带 output，所以落地走 compose 的 `--print` 产物。

### 候选 A：显式授权（`buildx bake --allow=network.host`）

- **A1（排除项）**：在覆写里给 `build.api.entitlements: ["network.host"]` —— bake 文件里确实出现 `"entitlements": ["network.host"]`，闸门仍拒，`ELAPSED=0.55s`，`PIPE_STATUS=1`：

```text
additional privileges requested: pass "--allow=network.host" to grant requested privileges
```

- **A3**：`docker compose --profile smoke build --print > /tmp/t21-bake.json` 之后 `docker buildx bake --allow=network.host -f /tmp/t21-bake.json api` → exit 0，暖缓存 `ELAPSED=23.99s`，末行 `#23 naming to docker.io/library/better-resume-api:latest`。
- **A 全栈（暖）**：`docker compose --profile smoke build --print | docker buildx bake --allow=network.host -f -` → exit 0，`ELAPSED=30.12s`。
- **A 全栈（`--no-cache`）**：同一管道加 `--no-cache` → `PIPELINE_EXIT=0`，`ELAPSED_SECONDS=65`，`uv sync` / `pnpm install` 的重跑步骤真的执行（非全 CACHED）。

### 候选 B：`build.network` 改 default

覆写文件（`/tmp/t21-b-override.yaml`，不入库）把 migrate/api/worker/fake-llm/nginx 的 `build.network` 改成 `default`：

- **B 全栈（暖）**：`COMPOSE_FILE=compose.yaml:/tmp/t21-b-override.yaml docker compose --profile smoke build` → exit 0，`ELAPSED=34.12s`，末三行 `Image better-resume-api Built` / `Image better-resume-nginx Built` / `Image better-resume-api Built`。
- **B 全栈（`--no-cache`）**：同上加 `--no-cache` → exit 0，`ELAPSED_SECONDS=69`。

网络可达性探针（无 cache mount、`--no-cache`，容器内真取 `https://pypi.org/simple/uv/` 与 `https://registry.npmjs.org/`）：

```text
default 网络        -> pypi 200 / npm 200   (ELAPSED=2.96s, EXIT=0)
host   网络+授权    -> pypi 200 / npm 200   (ELAPSED=2.75s, EXIT=0)
宿主直连            -> pypi 200 / npm 200；经 127.0.0.1:7897 也 200（镜像站 docker.m.daocloud.io 401 = 可达）
```

### 定方向：候选 A

- 两个候选都 exit 0，网络都可达，耗时 65s vs 69s（噪声级）——**读数不区分**。
- 差别在运行面：A 保留 `compose.yaml` 现有的 `network: host`（WSL2 本地代理可达性的来源），且 **compose.yaml 零改动**；B 把所有人（含 CI）的构建网络换成 default，为此必须改 `compose.yaml` 的 build.network。
- 取 A：显式授权参数 + 不改 compose.yaml。P15-8 的「择不削弱运行面者」按此判定。

## 红（改动前）

```bash
cd '/root/better resume' && bash scripts/compose_smoke.sh
```

```text
== compose config is valid
PASS: docker compose config

== postgres + redis, then seed the smoke-fake model row
 ...
 Image better-resume-api Building 
#1 [internal] load local bake definitions
#1 reading from stdin 704B done
#1 DONE 0.0s
additional privileges requested: pass "--allow=network.host" to grant requested privileges

Command exited with non-zero status 1
ELAPSED=4.21s
```

退出码 1，卡在第一个构建步（`docker compose run --rm --build migrate`），栈都还没起来。

## 绿（改动后）

改动只有三个脚本的构建调用行（`git diff --numstat`：`compose_smoke.sh` 138+/31- 含本票外的 p15 建议 4 在飞改动；`fault_injection_drill.sh` 16+/12-；`kill_instance_drill.sh` 12+/9-），`compose.yaml` 零改动。

### 1. `bash scripts/compose_smoke.sh` → exit 0（60.89s）

```text
== compose config is valid
PASS: docker compose config

== build the stack images (bake with an explicit network.host grant)
#0 building with "default" instance using docker driver
#1 [internal] load local bake definitions
#1 reading from stdin 3.15kB done

== declared default: one-shot-migrate
  声明位 compose.yaml: command: ["alembic", "upgrade", "head"]
PASS: the one-shot migrate job leaves the schema at head
== declared default: spa-cache-headers
  声明位 deploy/nginx.conf: add_header Cache-Control
  GET / -> Cache-Control: no-store（声明 no-store）
  GET assets/index-ByEg2Orj.js -> Cache-Control: max-age=31536000, public, immutable（声明 immutable）
PASS: SPA and hashed assets carry the declared Cache-Control
== declared default: containers-non-root
  声明位 apps/api/Dockerfile: USER app
  api uid=999（禁止 0）
  worker uid=999（禁止 0）
PASS: api/worker run as the declared non-root uid
== declared default: ws-idle-timeout
  声明位 deploy/nginx.conf: proxy_read_timeout 300s
  运行中的 nginx:         proxy_read_timeout 300s;
PASS: the running nginx carries the declared read timeout
== declared default: dynamic-upstream
  采样 12 次，X-Instance-Id 命中 2 个（声明 >= 2）: 7d535b1dc9f5 d57ee1666692
PASS: nginx reached at least the declared number of api instances

shared quota: allowed=4/7 (capacity=4) scope=shared, redis_keys=1
PASS: a fresh identity's 7 requests release ~capacity (not 2x) with X-RateLimit-Scope: shared

== summary
ALL CHECKS PASSED (edge: http://127.0.0.1:8080; stop with: docker compose --profile smoke down -v)
ELAPSED=60.89s
```

### 2. `bash scripts/kill_instance_drill.sh` → exit 0（99.91s）

```text
== build the images (bake grants network.host; compose never does)
#0 building with "default" instance using docker driver
#1 [internal] load local bake definitions
#1 reading from stdin 3.15kB done
 ...
== interview across two instances, kill the serving one, finish on the survivor
login: 200 instance=f19d3b1acf2b
killed instance f19d3b1acf2b
nginx now routes to 13391976a65a (first healthy response after 6 ms in 1 attempts of 1s, kill -> recovery 373 ms)
replayed request on 13391976a65a: replayed=True score=55.0
report summary from the worker: 整体结构清晰，深度尚可；建议用数据说明取舍与结果。

== drill summary ==
instances: served=f19d3b1acf2b survivor=13391976a65a kill->recovery=373 ms
PASS: 会话在实例被 kill 后由另一实例接管，状态、分数与冻结报告全部一致
== shared rate limit still holds after the kill (one quota, not one per survivor)
shared quota after kill: allowed=4/7 (capacity=4) scope=shared, redis_keys=2
PASS: survivor judged against the shared bucket
ELAPSED=99.91s
```

### 3. `bash scripts/verify.sh --layer scripts` → exit 0

```bash
cd '/root/better resume'
export PATH="$HOME/.local/bin:$PATH"
export UV_CACHE_DIR='/root/better resume/.cache/uv'
export BR_DATABASE_URL='postgresql+asyncpg://better_resume:better_resume@127.0.0.1:5433/better_resume'
export BR_REDIS_URL='redis://127.0.0.1:6379/0'
bash scripts/verify.sh --layer scripts
```

```text
101 passed, 2 warnings in 8.82s
[10/12] for f in scripts/*.sh; do bash -n "$f" || exit 1; done; echo shell syntax ok
shell syntax ok
[11/12] uv run --project apps/api python scripts/check_scripts.py
script syntax ok (24 python scripts, SyntaxWarning treated as an error)
[12/12] uv run --project apps/api python scripts/verify_audit_evidence.py --structural
structure ok: 10 units / 122 issues / 340 citations
ALL PASS (12 commands) -- evidence: var/evidence/20261017T054838Z-scripts
EXIT=0
```

该层首次复跑红在两处本票写入路径外：`[8/12] ticket_frontier --check`（`T22-final-reanchor.md` 的 `Blocked by` 指向当时尚未创建的 T19）与 `[9/12] test_verify_script.py::test_every_audit_citation_is_corroborated_by_its_evidence`（`ai-09 ai_resilience/timeout.py:56-71` 随在飞改动漂移）。两处的外部票落定后复跑即 ALL PASS。

### 4. 运行形态零变化

```text
$ git diff --stat -- compose.yaml
(空：compose.yaml 未改，build.network 仍是 host，端口/副本数/nginx.conf 均未动)
```

被断言的五条部署默认值读数（见第 1 节原始输出）：`one-shot-migrate`、`spa-cache-headers`、`containers-non-root`、`ws-idle-timeout`、`dynamic-upstream` 全 PASS，值与 T15 一致（`no-store` / `immutable` / uid 999 / `proxy_read_timeout 300s` / 2 个 X-Instance-Id）。

## 实现决定交代

| spec 未覆盖、我自行拍定的决定 | 为什么这么拍 | 我明确没做的 |
| --- | --- | --- |
| 构建出口落成 `docker compose <profile> build --print \| docker buildx bake --allow=network.host -f -`，并删掉 `up`/`run` 上的 `--build` | compose 没有 `--allow`（`build --help` 无此参数），唯一能显式授予 `network.host` 的是 bake CLI 的 `--allow`；`-f -` 免落临时文件，`pipefail` 让两段任一失败都非 0 | 没自己拼 bake 文件、没引新依赖、没写包装脚本 |
| 三个构建栈脚本都改（票只要求 compose_smoke + 至少一个 drill） | P15-8 说三个脚本同受同一闸门影响；只改两个会把 fault drill 留在必红状态 | 没改 `deploy/nginx.conf`、没改运行面任何字段 |
| 保留 `export COMPOSE_BAKE=false`，把注释改成当前事实（v5.6.0 里已失效、仅对旧 compose 有效） | `apps/api/tests/test_drill_prereqs.py` 逐字钉住这一行，而该测试不在本票写入路径内；删掉会把它打红 | 没删这行、没改那个测试、没把注释写成「本次改动」式叙述 |
| **未**改 `compose.yaml`（方向 A 不需要动 build.network） | 读数里 A/B 都绿；A 保留既有的 host 构建网络能力且零改文件，B 需要改所有人共用的 build.network | 没用票里那条「仅当原型结论要求改 build.network」的条件写路径 |
| 构建步位置：smoke/kill drill 放在 migrate 之前、`up` 之前；fault drill 的 sentinel 模式放在 drill profile 的 `up` 之前 | 一次性 migrate 作业需要镜像已存在；sentinel 模式没有 migrate 步 | 没动三个脚本的步骤顺序、探针与断言 |

## 未验证项

- **CI（nightly）未跑**：本机 buildx 的 builder 接受 `--allow=network.host`（同一 entitlement 在改动前的 classic 路径上被接受过），但 compose 2.38.2 + runner 的 builder 是否同样接受，未在本机取得读数——而 CI 恰好走同一份 `verify.sh` / 同一个 `compose_smoke.sh`。
- **compose 2.38.2 上的 `build --print` 未验**：本机只有 v5.6.0；CI 走这条命令。
- **`fault_injection_drill.sh` 只改了构建调用行，未真跑**：全量含 5 个故障实验（各 20s）+ 20 分钟浸泡，sentinel 模式也未跑；本票只要求「至少一个 drill」，真跑的是 `kill_instance_drill.sh`。
- **`--no-cache` 不等于全新下载**：uv/pnpm 的 `RUN --mount=type=cache` 挂载在 `--no-cache` 下仍复用，所以冷构建（A 65s / B 69s）不是全新拉包耗时；真实网络可达性由独立探针（无缓存挂载、`--no-cache`）覆盖。
- **A/B 的耗时读数不构成方向依据**：两者都 exit 0 且网络都可达，65s vs 69s 在噪声级；定方向依据是「不削弱现有构建网络 + 零改 compose.yaml」。
- **未跑 `--layer all` 与后端全量 pytest**：本票只改 `scripts/`；全量读数按派活口径由出票方串行复跑（并行期共享库读数不可信，见 PROBLEMS P15-1）。
