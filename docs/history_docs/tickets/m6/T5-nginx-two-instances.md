# M6-T5 — nginx + 双 api 实例：compose 最终形态

- blocking：M6-T4
- 纪律：先写失败测试（红），再实现（绿）；**用真实 docker compose 验证，不做纸面配置**

## 目标

补齐 D07 的部署面：`nginx` 作为 SPA 与 API 的统一入口、`api` 可水平扩到 2 个实例、
`worker` 消费者就位、全部服务带健康检查与条件依赖、容器非 root。

## 交付物

- `apps/web/Dockerfile`：node 构建 → `nginx:1.27-alpine`，SPA fallback（`try_files`）+ `/healthz`
- `deploy/nginx.conf`：`/api` 反代到 `api:8000`（`proxy_set_header Upgrade/Connection` 支持 WS）、
  `/healthz`、SSE 相关（`proxy_buffering off`、`proxy_read_timeout` 提到 300s、`X-Accel-Buffering: no`）
- `compose.yaml`：
  - `api` 非 root（镜像内 `useradd` + `USER`），`deploy.replicas` 或 `--scale api=2` 均可跑
  - `worker` 服务（同一镜像、不同入口），健康检查用 Redis 心跳键
  - `nginx` 服务依赖 api 健康；端口 8080（避开本机已用的 80）
  - 条件依赖 `service_healthy`；密钥仍走环境变量（compose 只传 `{BR_DEEPSEEK_API_KEY:-{'}'}` 之类）
- `apps/api/Dockerfile`：非 root + 健康检查 + `uv sync --frozen` 缓存层
- 测试/证据：`scripts/compose_smoke.sh`（起栈 → 等 healthy → 走 nginx 打完整链路 → 打印各服务状态）
- 文档：README 的部署章节更新（端口、健康检查、扩缩容命令）

## 测试

| 用例 | 断言 |
| --- | --- |
| 起栈 | `docker compose up -d --wait` 全部 healthy（api/worker/postgres/redis/nginx） |
| 经 nginx 的 REST | `POST /api/v1/auth/session` 200（cookie 生效） |
| 经 nginx 的 SSE | 聊天流式经代理不缓冲（逐帧到达，含心跳注释帧） |
| 经 nginx 的 WS | `/api/v1/media/transcribe` 升级成功（101） |
| 双实例 | `--scale api=2` 时 nginx 轮询到两个实例（日志/实例 id 断言） |
| 非 root | `docker compose exec api id -u` ≠ 0 |
| 密钥 fail-fast | 不注入 key 时 api 启动但 /models 诚实标记未配置（不崩溃） |

## 验收

| 命令 | 期望 |
| --- | --- |
| `bash scripts/compose_smoke.sh` | 全部 PASS，输出各服务 health 与三条链路结果 |
| 冷启动 | 记录了首次构建耗时（验收文档里写明环境） |

## 不做

- 不做 TLS/证书（本地 compose）；不做蓝绿发布；不做 nginx 缓存层（SSE 场景不需要）。

