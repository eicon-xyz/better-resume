# M0 待确认项（决策请拍板，我不自行决议）

## 0. 结论回填（2026-09-13 已拍板）

| 编号 | 你的决定 | 落地情况 |
| --- | --- | --- |
| D-A | **A1** | uv 0.12.7 装到 `/root/.local/bin`，Python 3.12.14 就位（沙箱内需 `UV_CACHE_DIR` 指向工作区，已记入 ACCEPTANCE.md） |
| D-B | 给了 GitHub 主页 | 采用 repo-local 身份 `eicon-xyz <eicon-xyz@users.noreply.github.com>`（未动全局配置，随时可改） |
| D-C | 照准 | compose 中 redis 不发布宿主端口；api 8000 / postgres 5432 |
| D-D | 照准 | `skills/` 仅 `.gitkeep`，知识库内容留 M6 |
| D-E | 照准 | CI 用 node 22（与本地 v22.23.2 一致） |
| D-F | **算** | 已产出 `docs/resume/M0-resume-draft.md`（骨架期口径，亮点条目待 M1–M4 回填） |
| D-G | 同意建议 | compose 写官方镜像名；本机用 daocloud 镜像 retag 补同名（`postgres:16-alpine` / `redis:7-alpine`） |
| D-H | 照准 | M0 无 users 表，dev 直发会话端点；`SessionRef` 只含 `chat|interview` |
| D-I | 照准 | Python 包 `better_resume`；web 包 `@better-resume/web` |
| 提案 | 同意 | T1–T9 全部执行完毕，证据见 `ACCEPTANCE.md` |

> 用户已确认本表结论与 M0 验收证据（2026-09-13）。

---
## D-A 工具链安装（阻塞 T1 起全部后端票）

事实：本机 `python3` = 3.10.12，**无 python3.12、无 uv**（D02/D17 要求 Python 3.12 + uv）；
`node` v22.23.2、`pnpm` 11.20.0、`docker` 29.6.2 + compose v5.3.1 已就绪。

| 选项 | 做法 | 代价 |
| --- | --- | --- |
| A1（推荐） | 官方脚本装 uv 到 `/root/.local/bin`，再 `uv python install 3.12` | 需要一次沙箱放宽（写 workspace 之外） |
| A2 | `UV_INSTALL_DIR` 指向仓库内 `.tools/`（加 .gitignore） | 不越沙箱，但仓库目录里多一个工具目录 |
| A3 | 后端命令全走 `ghcr.io/astral-sh/uv` 容器 | 本地命令与 CI 不再等价，最不推荐 |

## D-B git 提交身份（阻塞 T1 的提交）

事实：`/root/.gitconfig` 不存在，`user.name` / `user.email` 均未配置（`git config --global --list` 报错）。
请给 name/email；或允许我先用 repo-local 占位身份（后续可改）。

## D-C 宿主端口

事实：本机 6379 已被容器 `dataset-local-redis` 占用；3306/5672/9000/9001/15672 同样被占用；
5432、8000 空闲。
提议：compose 中 redis 不发布宿主端口（容器网络内互访即可），api 8000、postgres 5432。

## D-D skills/ 占位 vs「skills 不在 M0」

文档张力：完成标准要求「monorepo 结构符合 D08（… / skills 占位）」，
范围又写「skills/ 知识库不在 M0（§12.4 归 M6），不要顺手建」。
提议：只建空目录 + `.gitkeep`（满足 D08 结构），知识库内容一律 M6（D13）。

## D-E CI Node 版本

本机 node v22.23.2；kickoff 写的是「node20」。提议 CI 用 22 与本地一致；
若你要求 20，请确认（本地仍 22，命令相同）。

## D-F D14「每 M 结束更新简历草稿」

需要：简历草稿文件位置、是否由我在 T9 起草。若无，M0 验收清单里就不含该项。

## D-G 镜像/网络（阻塞 T6 的 api 镜像构建）

事实：Docker Hub 直连失败（`registry-1.docker.io` TLS EOF）；daocloud 镜像实测可用
（`docker.m.daocloud.io/library/postgres:16-alpine` 拉取成功）；`pypi.org`（200）、
`registry.npmjs.org`（200）可直连（经本机 7897 代理）；本机已缓存
`docker.m.daocloud.io/library/redis:7-alpine`、`python:3.12-slim`、`ghcr.io/astral-sh/uv:latest`。
提议：compose 写官方镜像名（仓库可移植），本机用镜像拉取 + `docker tag` 补齐同名本地镜像；
若你希望我改 `/etc/docker/daemon.json`（registry-mirrors，需沙箱放宽 + 重启 docker），请明确授权。

## D-H M0 的 identity / conversation 形态

- identity：M0 不建 users 表，`POST /api/v1/auth/session` 为 dev 直发会话（body `{user_id}`），
  `/auth/me`、`DELETE /auth/session` 齐活；真实登录与用户表留 M1。可否？
- conversation：§12.1 写 `SessionRef = ("chat"|"agent"|"interview", session_id)`，
  但 D09 砍掉独立 Agent 会话 -> 提议 M0 的 `SessionRef` 只含 `chat|interview`。

## D-I 命名

提议 Python 包名 `better_resume`（`apps/api/src/better_resume/`）；web 包名 `@better-resume/web`。