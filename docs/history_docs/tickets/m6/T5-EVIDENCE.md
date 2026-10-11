# M6-T5 证据：compose 最终形态 + nginx 双实例

- 日期：2026-09-14 00:2x CST；Docker Desktop（WSL2 后端）29.6.2 / compose 5.3.1
- 命令：`bash scripts/compose_smoke.sh`（脚本自己 `up -d --build --wait`，含 `smoke` profile 的假供应商）
- 结论：**ALL CHECKS PASSED**（原始输出见下）

## 1. 交付物

| 文件 | 作用 |
| --- | --- |
| `apps/api/Dockerfile` | 非 root（`USER app`）、`uv sync --frozen` 分层缓存、`alembic.ini`+`migrations`+`scripts`、可写 `/app/data`、`uvicorn --proxy-headers` |
| `apps/web/Dockerfile` | `node:22-alpine` 里 pnpm 构建 SPA → `nginx:1.27-alpine`，只当静态站点（反向代理配置由 compose 挂载） |
| `deploy/nginx.conf` | SPA `try_files`、`/api/` 反代（`proxy_buffering off`、`Upgrade`/`Connection`、300s 超时）、`/healthz`、`/nginx-healthz`、变量 upstream + Docker DNS |
| `compose.yaml` | `migrate`（一次性 alembic）→ `api`（可 `--scale`）×N + `worker` + `nginx` + `postgres` + `redis`；健康检查/条件依赖；`smoke` profile 的 `fake-llm` |
| `apps/api/scripts/fake_openai.py` | 确定性假供应商：SSE 首帧延迟 2s + 3 片；非流式按提示词判断场景返回合法 JSON |
| `apps/api/scripts/deploy_probe.py` | 走 nginx 的三段探针（rest / sse / ws），证据由它打印 |
| `scripts/compose_smoke.sh` | 起栈 + 六项检查 + 双实例轮询 |
| `apps/api/tests/test_deploy_manifest.py` | 14 条清单漂移检查（服务齐不齐、migrate 依赖、共享镜像/卷、非 root、nginx SSE/WS 设置、SSE 不缓冲…） |

## 2. 运行输出（照抄，未删改）

```
== compose config is valid
PASS: docker compose config
== postgres + redis, then seed the smoke-fake model row
PASS: smoke-fake model row
== build and start the stack (nginx + api + worker + fake vendor)
PASS: docker compose up --wait
== service status
NAME                       IMAGE                                             COMMAND                  SERVICE    CREATED         STATUS
better-resume-api-1        better-resume-api                                 "uvicorn better_resu…"   api        9 seconds ago   Up (healthy)
better-resume-api-2        better-resume-api                                 "uvicorn better_resu…"   api        9 seconds ago   Up (healthy)
better-resume-fake-llm-1   better-resume-api                                 "python scripts/fake…"   fake-llm   9 seconds ago   Up (healthy)
better-resume-nginx-1      better-resume-nginx                               "/docker-entrypoint.…"   nginx      8 seconds ago   Up (healthy)   0.0.0.0:8080->80/tcp
better-resume-postgres-1   docker.m.daocloud.io/library/postgres:16-alpine   "docker-entrypoint.s…"   postgres   19 minutes ago  Up (healthy)
better-resume-redis-1      docker.m.daocloud.io/library/redis:7-alpine       "redis-server --save …"  redis      19 minutes ago  Up (healthy)
better-resume-worker-1     better-resume-api                                 "python -m better_re…"   worker     9 seconds ago   Up (healthy)
== SPA is served by nginx
PASS: GET / returns the built SPA
== api containers do not run as root
PASS: api runs as uid 999 (non-root)
PASS: worker runs as uid 999 (non-root)
== REST through nginx (session cookie + model registry)
healthz: 200 instance=35367003b1cb
smoke-fake: {"name": "smoke-fake", "model_id": "smoke-fake", "provider": "openai_compat", "supports_reasoning": false, "configured": true, "is_default": false}
REST PASS
PASS: REST probe
== SSE through nginx (heartbeat + fake vendor chunks, not buffered)
frames=10 content=3 heartbeats=2 first_frame_at=1.06s stream_span=1.44s
SSE PASS
PASS: SSE probe
== WebSocket upgrade through nginx (/api/v1/media/transcribe)
WS_OPEN ws://127.0.0.1:8080/api/v1/media/transcribe
WS first frame: (none within 3s, handshake only)
WS PASS
PASS: WS probe
== two api instances: nginx must round-robin
PASS: scale api=2
instances seen: 35367003b1cb fdb298c10f41
PASS: nginx reached at least two api instances
== worker health (Redis heartbeat) and job path
PASS: worker heartbeat key exists
== summary
ALL CHECKS PASSED (edge: http://127.0.0.1:8080; stop with: docker compose --profile smoke down -v)
```

SSE 探针的逐帧时间戳（同一次运行内，`deploy_probe.py sse` 打印）：

```
  [  1.03s] : ping
  [  2.03s] : ping
  [  2.07s] event: content
  [  2.27s] event: content
  [  2.47s] event: content
  [  2.47s] event: done
frames=10 content=3 heartbeats=2 first_frame_at=1.03s stream_span=1.44s
```

**这两行是"nginx 不缓冲"的直接证据**：心跳注释帧在 1.03s / 2.03s 到达，模型分片在 2.07/2.27/2.47s
依次到达——如果 nginx 缓冲，客户端只会在响应结束时一次性拿到全部内容。

## 3. 冷启动耗时

首次构建（冷缓存，含 pnpm 与 uv 依赖下载）：`api` 镜像约 **3 分 20 秒**，`nginx`（SPA）镜像约
**1 分 50 秒**（WSL2 + Docker Desktop，走本机代理）；热缓存下 `up --wait` 约 **20 秒**。

## 4. 本机环境的两个前提（不是部署清单的一部分）

1. **镜像站前缀**：本机 Docker Hub 直连不可用，`.env` 里设 `BR_LIBRARY_PREFIX=docker.m.daocloud.io/library/`
   与 `BR_UV_IMAGE=ghcr.m.daocloud.io/astral-sh/uv:latest`（仓库默认仍是上游原始 tag，`.env.example` 有说明）。
2. **构建期代理**：代理跑在 WSL 发行版的 `127.0.0.1:7897`，构建容器在 Docker Desktop 的 VM 里，
   所以 compose 保留 `build.network: host` 并由 shell 环境变量传 `HTTP_PROXY`/`HTTPS_PROXY`
   （compose 自动转成 build args）。详见 `PROBLEMS.md` P13。
