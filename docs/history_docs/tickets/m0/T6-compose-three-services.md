# T6 — docker compose 三服务 + 健康检查

- blocking：T2（api 镜像需要应用与 /healthz）

## 目标

`docker compose up -d --wait` 后 postgres / redis / api 三服务全部 healthy。

## 交付物

- `compose.yaml`：postgres（`pg_isready`）、redis（`redis-cli ping`）、api
  （`curl -fsS localhost:8000/healthz`），depends_on 用 `condition: service_healthy`
- `apps/api/Dockerfile`：uv 多阶段构建（uv.lock 冻结安装、非 root 用户、无缓存残留）
- `.env.example`：POSTGRES_USER/PASSWORD/DB、DATABASE_URL、REDIS_URL、API_PORT、日志级别；
  开发默认值可直接跑，真实密钥只走环境变量
- `.dockerignore`；`docker compose config -q` 通过

## 验收

| 命令 | 期望 |
| --- | --- |
| `docker compose up -d --wait` | 三服务 `(healthy)`，退出码 0 |
| `docker compose ps --format json` | 三个 `Health: healthy` |
| `curl -fsS localhost:8000/healthz` | `{"status":"ok"}` |
| `docker compose down` | 干净退出，无残留容器 |

## 形态提议（待确认）

- 宿主端口：api 8000、postgres 5432；**redis 不发布宿主端口**（本机 6379 已被
  `dataset-local-redis` 占用，见 OPEN-QUESTIONS D-C）。
- 镜像源：本机 Docker Hub 直连失败，但 daocloud 镜像可拉（已实测
  `docker.m.daocloud.io/library/postgres:16-alpine` 成功）；compose 里仍写官方镜像名，
  本机用 retag/加速拉取（OPEN-QUESTIONS D-G）。
- worker / nginx 不建（M0 扩展定义）。

## 不做

- 不做生产优化、不做 compose profiles、不做数据卷导出脚本。
