# 交接文档（better-resume）

> 写给下一个窗口/接手的人：先读仓库根 **`GLOSSARY.md`**（域词汇表/术语）与 **`AGENTS.md`**（项目全貌 / 技术栈 / 规范），
> 再读**在飞阶段**的票据 `docs/tickets/<stage>/README.md`；已收口阶段的一切（票据 / 验收包 / 问题台账 / 经验流水）
> 归档在 `docs/history_docs/`——**那是历史，不是当前状态**。

## 1. 当前状态

**`main` = `353b4b5`（CI 绿），没有挂起的 PR，工作区无在飞阶段。**

- 已合并：M0–M6、V、P1–P10。代码即事实：验证入口 `bash scripts/verify.sh --list`。
- 验证网：CI 双 job 与本地走同一份分层命令（`scripts/verify.sh`）；`nightly`（每日 02:30 UTC，deploy + quick fault）
  与 `weekly-full`（周日 03:00 UTC，全量故障 + 60min 浸泡）是定时兜底。`schedule` 只认默认分支。
- 收口口径：`bash scripts/verify.sh --layer all` 全绿 + 后端全量 pytest（带 `BR_*` env、`--junitxml` 读数）。

## 2. 仓库与流程约定

- `apps/api`（FastAPI + SQLAlchemy async + Alembic + structlog）、`apps/web`（React 19 + Vite）、
  `docs/`（决议 / 交接 / 审计 / 容量报告）、`skills/`（repo-map + 模块 SKILL.md + 生成式 API 索引）。
- **协作流程（用户明确要求，永久生效）**：每个阶段**先出提案**（范围/不做/交付物/测试/验收口径）→ 用户确认 →
  红-绿 TDD 执行 → 交**验收包**（ACCEPTANCE：可复跑命令 + 原始输出 + 未验证项 + 偏差）→ **由用户验收**。
  **AI 不自行宣布完成、不擅自提交/推送/开 PR/合并**；验收通过且用户明确下令后才动 git。
- **文档纪律**：所有文档与代码注释只描述**当前状态**，不记录修改历史；临时阶段划分与被取代的决策不留痕。
- 纪律：只 mock 系统边界（LLM/时钟/Redis/讯飞/浏览器音频/IPC）；小步提交说 WHAT；难题即时记票据的 `PROBLEMS.md`；
  真机凭据只进 gitignored `.env`；不允许"默认关闭、没人跑"的死分支。

### 归档约定

- **在飞阶段** → `docs/tickets/<stage>/`（README 提案 / ACCEPTANCE / PROBLEMS / EVIDENCE）。
- **阶段收口后** → 整个目录移到 `docs/history_docs/tickets/<stage>/`；经验教训与状态流水进 `docs/history_docs/`。
- 历史档不是当前状态：排查"现在该怎么写"不要引用它，改代码前看代码本身与 `skills/`。

## 3. 怎么把这台机器跑起来

```bash
export PATH="$HOME/.local/bin:$PATH"          # uv 在 ~/.local/bin，root 新 shell 默认没有
export UV_CACHE_DIR='/root/better resume/.cache/uv'

# 后端测试（必须显式导出测试库地址，否则依赖 DB 的用例会 skipped）
cd '/root/better resume/apps/api'
export BR_DATABASE_URL='postgresql+asyncpg://better_resume:better_resume@127.0.0.1:5433/better_resume'
export BR_REDIS_URL='redis://127.0.0.1:6379/0'
uv run pytest -q --junitxml=/tmp/x.xml        # 例数看 xml 读数，别抄进文档

# 前端
cd '/root/better resume' && pnpm -C apps/web test --run     # 必须从仓库根

# compose 栈（nginx :8080 = 唯一入口；api 无宿主端口，可 --scale）
export BR_SMOKE_KEY=smoke-fake-key BR_SSE_HEARTBEAT_SECONDS=1
docker compose up -d --wait --scale api=2
docker compose --profile smoke down -v        # 停栈

# 三个验收脚本（都会自己起栈）
bash scripts/compose_smoke.sh                 # 部署面：REST/SSE/WS/非 root/双实例轮询/worker 心跳
bash scripts/kill_instance_drill.sh           # kill 正在服务的实例，状态/报告一致
bash scripts/fault_injection_drill.sh         # 5 个故障实验 + 浸泡（--quick 为 2 分钟浸泡）

# 真机探针（各消耗真调用，受 BR_REAL_CALL_BUDGET 守卫）
uv run python -m scripts.fault_probe fault --scenario redis-partition --seconds 20
uv run python -m scripts.fault_probe fault --scenario redis-failover  --seconds 20
uv run python scripts/media_smoke.py --paraformer-rt-real --wav ../../data/audio/p1c-multi-sentence-16k.wav
uv run python scripts/assembler_real_probe.py        # 真机增量包回放句池
uv run python scripts/v3_ws_probe.py --realtime      # 穿 nginx 的增量时序 + 关闭码

# 单一入口（CI 与本地同一份命令）
bash scripts/verify.sh --list          # 全部层与命令
bash scripts/verify.sh --layer all     # 本地收口（条数看 --list/--dry-run，别抄进文档）
python3 scripts/verify_audit_evidence.py --strict   # 审计收口：逐字核对引文（partial 也算失败）
```

人工测试只有一处入口：**`docs/MANUAL-TESTING.md`**（统一清单，§1 为必测）。

## 3b. 审计与验证工具

| 东西 | 一句话 |
| --- | --- |
| `docs/audit/MODULE-AUDIT.html` | 模块设计审计的**渲染产物**（10 个单元，每条带 `文件:行号` 与原文摘录）；`python3 scripts/build_module_audit.py` 重新生成 |
| `docs/audit/units/*.json` | 审计**数据**——渲染器的输入；改问题清单改这里，不要手改 HTML |
| `docs/history_docs/audit/FIXES.md` | 历史：已动手的审计条目修复台账 + 环境改进记录 |
| `docs/audit/CONTRACT.md` | 审计**口径**：检查维度、危险信号、证据与写作红线、severity 分级 |
| `scripts/verify_mutation.sh` | **变异证明**：断言"基线绿 → 变异红 → 恢复绿"，真看退出码并在恢复后校验 sha256 |
| `scripts/verify_audit_evidence.py` | 引证核对分两层：**结构层总是跑**（字段齐全 + 引用的文件/行号存在）；**逐字层**默认只报告，`--strict` 时 partial 也算失败 |
| `scripts/check_scripts.py` | 两个脚本目录的语法扫描（`SyntaxWarning` 当错误处理） |
| `GLOSSARY.md` | 域词汇表（**先读它**）；术语以外的实现细节不进这个文件 |
| `docs/agents/subagents.md` | 用子智能体干活的操作约定 |

## 4. 本机环境事实与坑

> 本节是**环境事实的单一真相源**：`AGENTS.md` 只留会"静默把事情做错"的几条（uv cache、BR_* 导出、junitxml、ffmpeg、httpx 兜底），
> 其余（端口表、构建代理与镜像前缀、WSL 掉线、22 端口、`gh` 证书、volume remount）以本节为准。

| 事实 | 影响 / 做法 |
| --- | --- |
| **本地 `main` 可能过期** | `git pull --ff-only` 在没有 upstream 时只打印提示、**不会拉取**。收口前先 `git fetch && git merge --ff-only origin/main`，或先 `git branch --set-upstream-to=origin/main main` |
| WSL2 + Docker Desktop（VM 与发行版不同网络） | 构建要 `build.network: host` + shell 里带 `HTTPS_PROXY=http://127.0.0.1:7897`（compose 会自动转成 build args）；**不要**往 `~/.docker/config.json` 写 proxies。buildx ≥ 0.37.2 会对 `network.host` 要授权，所以本机**人手**敲 `docker compose build/up --build` 时要带 `COMPOSE_BAKE=false`（构建栈的脚本已各自 export，无需手动） |
| **buildx ≥ 0.37.2 拒绝未授权的 `network.host`** | 症状：`additional privileges requested: pass "--allow=network.host"`，**构建还没开始就 exit 1**。根因：该版本起 bake 在 `--progress=rawjson` 下不再跳过权限同意检查；Compose 永远走 bake+rawjson 且只补 `--allow fs.read/security.insecure`，从不补 `network.host`，而 `compose.yaml` 为 WSL2 代理请求了它。做法：构建栈的脚本一律 `export COMPOSE_BAKE=false`（回到 classic 路径，它把 entitlements 直接交给 builder），由 `tests/test_drill_prereqs.py` 钉住 |
| **沙箱内 `docker build` 跑不了** | `workspace-write` 下 buildx 要写工作区外的 `/root/.docker/buildx/activity/` → permission denied；`docker build` / `docker compose build` / `up --build` 必然失败（`docker compose config` 与已构建镜像的 `up` 不受影响）。另：`docker compose build … \| tail` 会把退出码换成 `tail` 的 0（"exit 0" 是假象）。**要验构建面就推到 CI 跑** |
| Docker Hub 直连不通 | `.env` 里 `BR_LIBRARY_PREFIX=docker.m.daocloud.io/library/`、`BR_UV_IMAGE=ghcr.m.daocloud.io/astral-sh/uv:latest`（仓库默认仍是上游 tag） |
| **Docker Desktop 的 WSL 集成会掉线** | 症状：`docker` 命令突然消失（`/usr/bin/docker` 指向 `/mnt/wsl/docker-desktop/...`，挂载没了）。恢复：`/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe -NoProfile -Command Start-Process 'C:/Program Files/Docker/Docker Desktop.exe'`，等约 1 分钟后 `docker compose up -d --wait --scale api=2` |
| **出网 22 端口可能被拒** | `git push` 报 "Connection refused / 请检查权限"时先 `ssh -T git@github.com`：22 端口被拒不是仓库问题。改走 443：`git push ssh://git@ssh.github.com:443/<owner>/<repo>.git <branch>`，或写进 `~/.ssh/config`（Host github.com → HostName ssh.github.com, Port 443） |
| GitHub：SSH 可用、API 时断时续 | `git push` 正常；`gh pr create/api` 可能 SSL EOF（重试/稍后再试），必要时用 REST + `--body-file`。`gh run view --log` 需要可写的缓存目录：在沙箱里需 `export XDG_CACHE_HOME='/root/better resume/.cache'`，否则报 `creating cache entry: … permission denied` |
| 没有 ffmpeg | 转音频用 `uv run --with soundfile --with numpy python …` |
| pytest 输出被 `-q` 压掉摘要 | 一律 `--junitxml=/tmp/x.xml` 再解析 `tests/failures/errors`；**跑前先 rm 掉旧 xml** |
| 本机 `NO_PROXY` 含裸 IPv6 | httpx 构造时可能抛 `InvalidURL: Invalid port ':1]'`；所有新建 httpx client 都要兜底（`trust_env=False`） |
| 测试/脚本需 hermetic | 代理变量、PATH、DB 地址都算环境：断言不能依赖 shell 里恰好有什么 |
| 端口 | 原生测试库 Postgres **5433** / Redis **6379**；compose 内网 postgres 5432（不发布）、nginx 宿主 **8080** |
| **改过 volume 挂载的文件后 `restart` 会失败** | WSL2 bind-mount inode 失效（`no such file or directory`）→ 用 `docker compose up -d --force-recreate <svc>` 重新挂载，**不要**重启 Docker 引擎 |
| **`gh` 报「token invalid」多半是证书问题** | 代理（7897）没起时直连 HTTPS 被本机 Watt Toolkit 的中间人证书（CN=SteamTools Certificate）拦截、系统 CA 不认。修法：用 `openssl s_client -connect api.github.com:443 -servername api.github.com -showcerts` 的输出里抽出 `BEGIN CERT`→`END CERT` 段存成 `/tmp/chain.pem`，再 `export SSL_CERT_FILE=/tmp/chain.pem`（`git push` 走 ssh.github.com:443，不受影响） |

## 5. 凭据与密钥（务必遵守）

- **只放仓库根 `.env`（gitignored）**，绝不入库；`.env.example` 只写变量名。
- `.env` 里的 key：`BR_DEEPSEEK_API_KEY`（官方 DeepSeek）、`BR_DASHSCOPE_API_KEY`（阿里百炼）、
  `BR_ARK_API_KEY`（火山方舟，**账号未开通任何模型**，调用返回 404 `ModelNotOpen`，已弃用）、
  `BR_MEDIA__ASR_URL/ASR_MODEL/TRANSCRIPTION_ADAPTER`。
- **真假供应商的判定**：真实调用的响应里带 `usage`（流式需要模型行 `extra.stream_usage=true` 才会带）；
  假供应商（`apps/api/scripts/fake_openai.py` + `smoke-fake` 模型行）没有 usage。

## 6. 未验证 / 欠账（诚实清单）

- **讯飞 AST / 星云工作流真机**：无凭据，未验证（阿里实时 ASR 覆盖同类能力，非同一协议）。
- **百炼应用调用（星云的阿里等价物）**：adapter 已实现并合并，代码面有 10 条契约 × 3 实现 + 假 SSE 服务端证据；
  **真机调用全部失败**——供应商回 `InvalidParameter: Required parameter(AppId) missing or invalid`（两种端点相同）
  → **这条链路仍属未验证**，等确认应用是否已发布 / app_id 取值。
- **浏览器矩阵**：Safari/Firefox/蓝牙未测；长音频最长只验到 13.1s。
- **供应商 429**：真调用一次未触发；退避/重试路径仍是纸面推演。
- **单机 compose 上的哨兵 ≠ 生产级高可用**：三个哨兵同一台宿主、同一个 Docker 守护进程，宿主一挂全挂；
  也没做多可用区与脑裂治理。另一个**已探明的限制**：compose 的单机内嵌 DNS 在容器退出后不再解析服务名，
  哨兵会进 TILT 而拒绝 failover——所以演练用 `docker compose pause redis`（主不可达）而非杀容器，后者在本仓库无法验证。
- **>24 并发 / 真实 LB 抖动**：未测。
- **定时任务在合并后的默认分支上尚未跑满一轮**：`nightly`/`weekly-full` 的绿是在分支上实测的；
  合并后首个定时窗口前，默认分支的历史结论不继承。

## 7. 后续候选（都要先提案）

自动 Redis failover（哨兵/多端点）、>24 并发与供应商 429 行为、讯飞真机、浏览器矩阵。

## 8. 文件地图（找东西用这个）

```
GLOSSARY.md                             ← 域词汇表（术语；**接手先读这个**）
AGENTS.md                               ← 项目全貌/技术栈/命令/规范/TDD 纪律
docs/HANDOFF.md                         ← 本文档：当前状态 / 怎么跑 / 环境坑 / 未验证清单
docs/DECISIONS.md                       技术决议 D01–D22（冲突以它为准）
docs/agents/subagents.md                子智能体操作约定
docs/audit/                             模块设计审计：MODULE-AUDIT.html（产物）/ units/*.json（数据）/ CONTRACT.md（口径）
docs/history_docs/                      历史归档：tickets/**（各阶段票据+验收包+问题台账）、HANDOFF-archive.md、audit/FIXES.md
docs/tickets/<stage>/                   在飞阶段：README + ACCEPTANCE + PROBLEMS + EVIDENCE
docs/MANUAL-TESTING.md                  人工测试统一入口
docs/perf/capacity.md                容量报告
docs/resume/MN-resume-draft.md          各里程碑/P1 简历草稿
skills/repo-map/SKILL.md                "改 X 先看哪"（含两跳示例）
apps/api/src/better_resume/             后端源码（settings / llm_gateway / ai_resilience / interview_engine / jobs / media …）
apps/api/scripts/                       真机探针与一次性脚本
apps/api/tests/                         pytest（hermetic；test_source_hygiene.py 拦语法警告与转义反引号）
scripts/verify.sh                       单一验证入口（CI 与本地同一份命令）
scripts/compose_smoke.sh                部署面验收（含缓存头断言）
scripts/kill_instance_drill.sh          kill 实例硬验收
scripts/fault_injection_drill.sh        浸泡/故障注入
scripts/verify_mutation.sh              变异证明
scripts/check_scripts.py                两个脚本目录的语法扫描
.githooks/pre-commit                    可选提交前检查（git config core.hooksPath .githooks 启用）
compose.yaml + deploy/nginx.conf        部署最终形态
```
