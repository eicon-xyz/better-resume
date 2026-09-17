# 交接文档（better-resume · P1 阶段收口）

> 写给下一个窗口/接手的人：先读这一页与仓库根 **`AGENTS.md`**（项目全貌 / 技术栈 / 规范），
> 再读 `docs/tickets/p1-post-v/README.md`（当前阶段票据与进度）。
> 最后更新：2026-09-17（P1+P2 完成、浏览器手测第 3 轮通过、**用户已正式验收**；PR 流程进行中）。

## 1. 一句话状态

**M0–M6、V 阶段已合并进 main**（V = PR #7）；**P1（实时 ASR/真模型容量/阿里 API 补验/生产演练）与 P2（测试自动化 T1–T6）全部落地**，
分支 `p1/realtime-asr`（tip 见 `git log`，已全部推送；工作区干净）。**浏览器手测已通过（3 轮，修掉 P28/P29/P30）**，
**用户已于 2026-09-17 正式验收 P1+P2**（ACCEPTANCE §7 已回填）→ **PR #8 已开**（`p1/realtime-asr` → `main`）。
CI 首跑暴露 3 个只有干净 checkout/CI 才看得见的缺陷（**P31–P33**：本地 `--layer all` 漏 contract 层、fixture 断言不
hermetic、全仓格式），已逐条红-绿修完并复跑：`verify.sh --layer all`（**12 条命令**）全绿 —— 后端 **747** /
前端 **173** / contract **9/9** / 脚本 **23**（证据 `var/evidence/20260917T142720Z-all`）。
等 CI 双 job 绿 → 用户点头 → 合并。`.env` 默认 `paraformer-rt`（边说边出字）。
真机花费 ~185 次（P1 约定 200 封顶内；`verify.sh --layer real` 自带预算守卫）。

## 2. 仓库与流程约定

- `apps/api`（FastAPI + SQLAlchemy async + Alembic + structlog）、`apps/web`（React 19 + Vite）、
  `docs/`（决议/架构分析/各里程碑票据）、`skills/`（repo-map + 模块 SKILL.md + 生成式 API 索引）。
- **协作流程（用户明确要求，永久生效）**：每个阶段**先出提案**（范围/不做/交付物/测试/验收口径）→ 用户确认 →
  红-绿 TDD 执行 → 交**验收包**（ACCEPTANCE：可复跑命令 + 原始输出 + 未验证项 + 偏差）→ **由用户验收**。
  **AI 不自行宣布完成、不擅自合并**；验收通过后才开 PR / 合并 / 进下一阶段。
- 纪律：只 mock 系统边界（LLM/时钟/Redis/讯飞/浏览器音频/IPC）；小步提交说 WHAT；难题即时记
  `docs/tickets/mN/PROBLEMS.md`；真机凭据只进 gitignored `.env`；不允许"默认关闭、没人跑"的死分支。

## 3. 怎么把这台机器跑起来

```bash
export PATH="$HOME/.local/bin:$PATH"          # uv 在 ~/.local/bin，root 新 shell 默认没有
export UV_CACHE_DIR='/root/better resume/.cache/uv'

# 后端测试（注意：必须显式导出测试库地址，否则 5432 连不上）
cd '/root/better resume/apps/api'
export BR_DATABASE_URL='postgresql+asyncpg://better_resume:better_resume@127.0.0.1:5433/better_resume'
export BR_REDIS_URL='redis://127.0.0.1:6379/0'
uv run pytest -q          # 678 例；不导出 BR_* 时依赖 DB 的用例会 skipped（不会假装通过）

# 前端
cd '/root/better resume' && pnpm -C apps/web test --run     # 必须从仓库根；在 apps/api 下用 -C ../web

# compose 栈（nginx :8080 = 唯一入口；api 无宿主端口，可 --scale）
export BR_SMOKE_KEY=smoke-fake-key BR_SSE_HEARTBEAT_SECONDS=1
docker compose up -d --build --wait --scale api=2
docker compose --profile smoke down -v        # 停栈

# 两个验收脚本（都会自己起栈）
bash scripts/compose_smoke.sh                 # 部署面：REST/SSE/WS/非 root/双实例轮询/worker 心跳
bash scripts/kill_instance_drill.sh           # §12.4 硬验收：kill 正在服务的实例，状态/报告一致
bash scripts/fault_injection_drill.sh           # 5 个故障实验 + 浸泡（--quick 为 2 分钟浸泡）

# P1-D 生产形态演练（恢复动作在 finally，可安全重跑）
uv run python -m scripts.fault_probe fault --scenario redis-partition --seconds 20   # 网络分区：503/timeout 语义 + 自愈
uv run python -m scripts.fault_probe fault --scenario redis-failover  --seconds 20   # 主从切换：恢复时间 + worker 存活
# P1 真机探针（各 1 次真调用）
uv run python scripts/media_smoke.py --paraformer-rt-real --wav ../../data/audio/p1c-multi-sentence-16k.wav
uv run python scripts/assembler_real_probe.py        # 真机增量包回放句池（提交语义 + 已知边界）
uv run python scripts/v3_ws_probe.py --realtime      # 穿 nginx 的增量时序 + 关闭码

# 单一入口（P2-T1；CI 与本地同一份命令）
bash scripts/verify.sh --list          # 全部层与命令
bash scripts/verify.sh --layer all     # 本地收口（unit+contract+scripts = 12 条命令，747+173）
```

人工测试只有一处入口：**`docs/MANUAL-TESTING.md`**（统一清单，§1 为必测）。

- **P1 阶段新增**：`media/adapters/paraformer_rt.py`（百炼实时 ASR）、`scripts/assembler_real_probe.py`、
  `fault_probe.py` 的 `redis-partition` / `redis-failover` 两个场景、`data/audio/p1c-multi-sentence-16k.wav`（本地素材）。
- **V 阶段专属脚本**：`apps/api/scripts/real_model_smoke.py`（真模型四链路 + 失败面）、
  `scripts/load_test.py`（压测，带 `--tag`）、`apps/api/scripts/fault_probe.py` +
  `scripts/fault_injection_drill.sh`（浸泡/故障注入）、`apps/api/scripts/v3_ws_probe.py`（ASR 走 WS 端到端）。
- **契约漂移三件套**（改过后端模型必须一起跑）：`uv run python scripts/export_openapi.py`（apps/api 下）、
  `pnpm -C apps/web gen:api`、`uv run python scripts/extract_api_index.py --check`。

## 4. 本机环境事实与坑（踩过的，别再踩）

| 事实 | 影响 / 做法 |
| --- | --- |
| WSL2 + Docker Desktop（VM 与发行版不同网络） | 构建要 `build.network: host` + shell 里带 `HTTPS_PROXY=http://127.0.0.1:7897`（compose 会自动转成 build args）；**不要**往 `~/.docker/config.json` 写 proxies |
| Docker Hub 直连不通 | `.env` 里 `BR_LIBRARY_PREFIX=docker.m.daocloud.io/library/`、`BR_UV_IMAGE=ghcr.m.daocloud.io/astral-sh/uv:latest`（仓库默认仍是上游 tag） |
| **Docker Desktop 的 WSL 集成会掉线** | 症状：`docker` 命令突然消失（`/usr/bin/docker` 指向 `/mnt/wsl/docker-desktop/...`，挂载没了）。恢复：`/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe -NoProfile -Command Start-Process 'C:/Program Files/Docker/Docker/Docker Desktop.exe'`，等约 1 分钟后 `docker compose up -d --wait --scale api=2`（2026-09 实际踩过一次） |
| **出网 22 端口可能被拒**（2026-09-15 实测） | `git push` 报 "Connection refused / 请检查权限"时先 `ssh -T git@github.com`：22 端口被拒不是仓库问题。改走 443：`git push ssh://git@ssh.github.com:443/<owner>/<repo>.git <branch>`，或写进 `~/.ssh/config`（Host github.com → HostName ssh.github.com, Port 443） |
| GitHub：SSH 可用、API 时断时续 | `git push` 正常；`gh pr create/create api` 可能 SSL EOF（重试/稍后再试），必要时用 REST + `--body-file` |
| 没有 ffmpeg | 转音频用 `uv run --with soundfile --with numpy python …`（已把用户录音转成 `data/audio/v3-sample-16k.wav`） |
| pytest 输出被 `-q` 压掉摘要 | 一律 `--junitxml=/tmp/x.xml` 再解析 `tests/failures/errors`；**跑前先 rm 掉旧 xml**，否则读到陈旧结果 |
| 本机 `NO_PROXY` 含裸 IPv6 | httpx 构造时可能抛 `InvalidURL: Invalid port ':1]'`；所有新建 httpx client 都要兜底（`trust_env=False`），M3/V3 各踩一次 |
| 测试/脚本需 hermetic | 代理变量、PATH、DB 地址都算环境：断言不能依赖 shell 里恰好有什么（见 P15） |
| 端口 | 原生测试库 Postgres **5433** / Redis **6379**；compose 内网 postgres 5432（不发布）、nginx 宿主 **8080** |

## 5. 凭据与密钥（务必遵守）

- **只放仓库根 `.env`（gitignored）**，绝不入库；`.env.example` 只写变量名。
- 目前 `.env` 里有：`BR_DEEPSEEK_API_KEY`（官方 DeepSeek，V1/V2 用的就是它）、
  `BR_DASHSCOPE_API_KEY`（阿里百炼，V3/V4 用）、`BR_ARK_API_KEY`（火山方舟，**账号未开通任何模型**，
  调用返回 404 `ModelNotOpen`，已弃用）、`BR_MEDIA__ASR_URL/ASR_MODEL/TRANSCRIPTION_ADAPTER`。
- **这三个 key 都在对话里出现过 → 建议交接后轮换一遍**（轮换后只改 `.env` 即可，代码不用动）。
- **真假供应商的判定**：真实调用的响应里带 `usage`（流式需要模型行 `extra.stream_usage=true` 才会带，
  见 P19）；假供应商（`apps/api/scripts/fake_openai.py` + `smoke-fake` 模型行）没有 usage。

## 6. V 阶段逐票状态（证据入口）

| 票 | 状态 | 一句话 | 证据 / 复跑 |
| --- | --- | --- | --- |
| V1 真模型四链路 + 失败面 | ✅ | DeepSeek 真机：四链路 + 缺凭据 503 点名变量 | `V1-EVIDENCE.md`；`uv run python -m scripts.real_model_smoke --failure-probe` |
| V2 真模型容量 + 拐点 | ✅ | chat p50 1.9s（我们增量 ~30ms）；限流钉住 ~23 ok/s，c=80 拒绝路径 p50 134ms | `V2-EVIDENCE.md` + `docs/perf/M6-capacity.md` §2.4–2.6 |
| V3 语音识别真机 | ✅ | 百炼 Qwen-Audio-ASR-Flash（**批量**）：5.5s 音频 1.15s 出文本；WS 端到端 0.77s 收 final、干净关闭 1000 | `V3-EVIDENCE.md`；`media_smoke.py --qwen-asr-real --wav data/audio/v3-sample-16k.wav`；`scripts/v3_ws_probe.py` |
| V4 第二家 LLM 平台 | ✅ | 百炼 qwen-plus **零代码**接入，四链路 + 与 DeepSeek 对照 + P18 多副本复证 | `V4-EVIDENCE.md` |
| V5 浏览器人工手测 | ✅ | 用户本机 Chrome：两次不同句子**追加**显示、手写内容未被覆盖、TTS 正常 | `V5-EVIDENCE.md` |
| V6 浸泡 + 故障注入 | ✅ | redis-pause/restart 语义；worker 崩溃任务 59.3s 被接管；10 分钟 600 请求 0 失败 | `V6-EVIDENCE.md`；`bash scripts/fault_injection_drill.sh [--quick]` |

阶段问题台账：`docs/tickets/v1-verification/PROBLEMS.md`（P17–P21）。

## 6b. P1 阶段逐票状态（证据入口）

| 票 | 状态 | 一句话 | 证据 / 复跑 |
| --- | --- | --- | --- |
| P1-A 实时 ASR | ✅ 手测通过，待正式验收 | 百炼 Paraformer 实时：端到端首增量 **0.56s**、松手→final **1.1s**（修 P24 前 10.1s）；句池不被该供应商触发（直连 replace/archive） | `P1-A-EVIDENCE.md`；`scripts/v3_ws_probe.py --realtime` |
| P1-B 真模型容量 + 限流标定 | ✅ 待验收 | 24 并发真流 0 供应商错误；标定 `ai_call 6→2`、`answer 8→2`（红-绿 + 实证） | `P1-B-EVIDENCE.md` + `docs/perf/M6-capacity.md` §2.7 |
| P1-C 阿里 API 补验 | ✅ 待验收 | 多句真机（3 句、含供应商自我纠错）；句池真机包回放提交语义 PASS + 已知边界 | `P1-C-EVIDENCE.md`；`scripts/assembler_real_probe.py` |
| P1-D 生产形态演练 | ✅ 待验收 | 分区（503+Retry-After、恢复 0.2–2.2s）/ 主从切换（恢复 109ms、worker 存活）/ 浸泡 3600 请求 0 失败 | `P1-D-EVIDENCE.md`；`fault_probe.py fault --scenario redis-partition|redis-failover` |

阶段问题台账：`docs/tickets/p1-post-v/PROBLEMS.md`（P24–P27 + 验收轮新增 P28–P30）；阶段验收包：`docs/tickets/p1-post-v/ACCEPTANCE.md`。

**P1-A 浏览器手测已完成**（第 3 轮通过，2026-09-17）：实时出字 ✅、录音中打字原位保留 ✅；过程中修掉
P28（页面级合并层）→ P29（部署缓存头）→ P30（chat Composer 内部第三层合并）——全部红-绿 + 页面级回归用例，
结论与每轮记录在 `docs/MANUAL-TESTING.md` §5。

## 6c. P2 阶段逐票状态（测试自动化）

| 票 | 状态 | 一句话 | 证据 / 复跑 |
| --- | --- | --- | --- |
| T1 verify.sh 单一入口 | ✅（含 P31 修正） | 分层 unit/contract/coverage/deploy/fault/soak/real/scripts/all + --dry-run/--list；CI 双 job 已改调它；**all 层曾静默漏 contract**（P31，2026-09-17 修：抽 builder 复用 + 展开漂移测试） | `scripts/verify.sh`；`tests/test_verify_script.py`（钉 all ⊇ unit∪contract∪scripts） |
| T2 pytest markers | ✅ | --strict-markers + 默认 `-m 'not docker and not real'` | `tests/test_pytest_config.py` |
| T3 nightly/weekly | ✅（首跑等合并） | 公有仓库免费：nightly=deploy+quick fault；weekly=全量故障+60min 浸泡；YAML 本地已校验；**schedule 只认默认分支**，合并后自动首跑 | `.github/workflows/nightly.yml`、`weekly-full.yml` |
| T4 真机套件+预算守卫 | ✅（含 P32 修正） | BR_REAL_CALL_BUDGET=200、超预算/缺凭据非零退出、dry-run 列清单；音频生成器钉 sha256；**fixture 预检**（P32：缺文件/字节漂移都在花钱前 exit 2，`VERIFY_FIXTURE_AUDIO_DIR` 可覆盖） | `verify.sh --layer real`；`make_fixture_audio.py --check`；`tests/test_real_layer.py` |
| T5 脚本回归 | ✅ | 14/14 脚本 ≥2 契约（import 隔离/argparse/拒绝假装/同步性） | `tests/test_scripts_contracts.py` |
| T6 覆盖率两轮 | ✅ | 报告→底线：7 深模块 ≥90% 进 CI（缺数据=违规）；浅模块不设线 | `scripts/check_coverage_floors.py`；`coverage-report-round1.md` |

## 7. 可复用的经验教训（精华）

**契约与实现**
1. 实现 Protocol ≠ 满足契约：`wait()` 该阻塞却立即返回，类型检查全绿、端到端第一帧就断（P20）。
   新 adapter 必须跑一次真实链路，不能只看单测。
2. "可选字段"最容易静默丢失：流式 `usage` 需按平台请求（P19）——没有报错，只有空值。
3. 缓存要有 TTL 或跨进程失效：多副本下"只在本地失效"= 配置漂移（P18，8 个 503 一度被误判为供应商限流）。
4. 缺配置要报"不可用"，不是"你未登录"：Redis 挂了应是 503 + Retry-After，不是 500（P17）。
5. 过期视图比慢视图更糟：热层读缓存必须写路径失效（M6 P6）。
6. 未 await 的协程恒为真值 → "检查"变"永远通过"（M6 P8）；测试里加 RuntimeWarning 断言很便宜。

**分布式与异步**
7. 先查结果再抢锁：否则 owner 释放瞬间会出现"空档重跑"（M6 P2）。
8. 队列要兼容下限版本：Redis 6.0 没有 `XAUTOCLAIM`/带 IDLE 的 `XPENDING`，且 `XCLAIM` 只返回条目列表（M6 P7）。
9. worker 不能死于依赖抖动：阻塞读被取消会包装成 TimeoutError 逃出循环（M6 P9）。
10. 崩溃恢复时间 = 接管阈值本身（实测 59.3s ≈ `min_idle_ms=60s`），不要美化。

**部署与验证**
11. compose 必须有迁移步骤（一次性 `migrate` 服务 + `service_completed_successfully`），否则新卷直接 500（M6 P10）。
12. 非 root + 共享卷：容器里建不了 `data/`、多副本看不到同一份上传都会 500（M6 P11）。
13. nginx 只在启动解析 upstream → 变量 + `resolver 127.0.0.11` 才能 `--scale` 生效（M6 P12）。
14. **本地验收清单必须逐条镜像 CI**：漏了 `pnpm gen:api` → 本地"全绿"、CI 直接红（M6 P16）。
15. 测试必须自带环境（P15）：依赖 shell 里的代理变量/PATH/DB 地址的断言，在别人机器上会静默失效；
    干净 shell 才是真验收环境。
16. 端到端探针本身也会骗人：5s 超时把"接管耗时"量成了探针上界（V6/P21 周边）；数字要写清口径。

**流程**
17. 提案先行、验收包交付、由人拍板——本项目已经因此两次避免了"假绿"（M6 收尾、V 阶段）。

**验证与演练（P1 阶段补充）**
18. **连接参数不能信库默认值**：`websockets` 的 `close_timeout` 默认 10s，供应商不回关闭帧 → 松手后干等 10 秒（P24）。
19. **证据工具本身要先被校准**：探针"发完才收"会把增量时序塌缩（P25）；漏 cookie 会把 503 读成 401（P27）；
    演练的恢复动作必须放 `finally`，否则一次崩溃就把栈留在故障态。
20. **兜底 try 要罩住循环里的每一次依赖调用**：心跳写漏在 try 外，Redis 抖动就让 worker 退出（P26，M6 P9 的补完）。
21. **单身份压测测的是"我们的桶"**：进程内限流 × N 副本 = 配额 ×N；要压供应商必须多身份并行（P1-B §2.7）。

**验收轮补充（P28–P30）**
22. **一个语义可能活在多层**：转写合并 = store→页面→**组件内部 prop-effect**；P28 改了两层仍复发，P30 才补上
    chat Composer 这层。改任何合并语义，先 grep 调用点清零。
23. **测试缝贴着用户路径不够时，贴着组件也来一份**：store 级页面测试全绿，浏览器照样复现——因为组件内部
    合并由 prop 逐事件驱动，store 灌事件测不到（P30 的缝缺口）。
24. **部署不发 Cache-Control = 修了个寂寞**：index.html 无头 → 启发式缓存 → 用户跑上一版 bundle，症状与代码
    bug 肉眼难分（P29）。判定链：nginx access log 拉的是哪个 hash → 容器产物 md5 vs 本地 build。

**PR 首跑补充（P31–P33）**
25. **收口脚本的"标签"与"展开"会各自漂移**：`--list` 写着 `all = unit + contract + scripts`，`all)` 实际只跑
    unit+scripts（P31）——于是"本地全绿、CI 红"（M6 P16）原地复活。写"本地收口"之前先 `--dry-run` 看它**到底要跑什么**；
    回归测试钉展开，不钉标签。
26. **测试断言不许引用"本机恰好存在的文件"**：`data/` 是 gitignored，fixture 断言在干净 checkout 必红（P32）。
    需要本地产物的校验，放进那一层自己的预检（real 层：**花钱之前** exit 2），单测只测 hermetic 的"缺失即拒绝"。

## 8. 未验证 / 欠账（诚实清单）

- **讯飞 AST / 星云工作流真机**：无凭据，未验证（P1-C 用阿里实时 ASR 覆盖同类能力，非同一协议）；
  星云的阿里等价物（百炼应用调用）**等用户提供 app_id**。
- ~~真实浏览器手测（P1-A）~~ **已完成**（第 3 轮通过，顺带修出 P28/P29/P30）。仍待：浏览器矩阵（Safari/Firefox/蓝牙）、>30s 长说的实时表现。
- **供应商 429**：P1 阶段 177 次真调用一次未触发；退避/重试路径仍是纸面推演。
- **>24 并发 / 自动 Redis failover / 多可用区 / 真实 LB 抖动**：未测；应用是单 `BR_REDIS_URL`，自动切换需改代码。
- 浏览器矩阵（Safari/Firefox/蓝牙）延续未验证；长音频最长只验到 13.1s。

## 9. 交接动作清单

1. ~~**用户**：正式验收 **P1 + P2**~~ ✅ **已完成（2026-09-17）**：用户验收通过，结论回填
   `docs/tickets/p1-post-v/ACCEPTANCE.md` §7（浏览器手测第 3 轮 ✅，见 `docs/MANUAL-TESTING.md` §5）。
2. **用户**（小事仍挂着）：轮换三个 key（对话里出现过）；端到端验证"星云等价物"时给百炼应用 **app_id**。
3. **我**（PR 流程，**进行中**）：**PR #8 已开**（`p1/realtime-asr` → `main`，正文 = ACCEPTANCE.md）。
   首跑 backend 红（P31–P33，本地看不见的三层）→ 已红-绿修完并复跑 `--layer all` 12 条命令全绿 → 复跑 CI → 用户点头 → 合并：
   ```bash
   cd '/root/better resume'
   # 本机 gh 的 TLS：7897 代理没起时，直连被 Watt Toolkit 中间人拦截，需信任其证书链
   #   openssl s_client -connect api.github.com:443 -servername api.github.com -showcerts </dev/null | \
   #     awk '/BEGIN CERT/,/END CERT/' > /tmp/chain.pem
   export SSL_CERT_FILE=/tmp/chain.pem; unset HTTPS_PROXY HTTP_PROXY
   gh pr checks 8 --watch                 # backend/frontend 双 job（含 coverage 底线步）
   gh pr merge 8 --merge                  # 用户点头后
   # 22 端口被拒时：git push ssh://git@ssh.github.com:443/eicon-xyz/better-resume.git <branch>
   cd apps/api && uv run pytest -q --junitxml=/tmp/main.xml   # main 复跑 747
   # 合并当晚 02:30 UTC：nightly 首跑（schedule 只认默认分支）；次日 gh run list + artifacts
   ```
   **注意**：历史清理时删光了 29 条 run → GitHub 上 workflow 曾"注销"（`gh workflow list` 为空）；PR 事件会重新注册，
   nightly/weekly 要等合并后由 schedule 注册。
4. 后续候选（都要**先提案**）：自动 Redis failover（哨兵/多端点）、>24 并发与供应商 429 行为、讯飞真机、浏览器矩阵。

## 10. 文件地图（找东西用这个）

```
AGENTS.md                               ← 项目全貌/技术栈/命令/规范/TDD 纪律（接手先读）
docs/HANDOFF.md                         ← 本文档
docs/DECISIONS.md                       17 项技术决议（冲突以它为准）
docs/tickets/p1-post-v/                 P1 阶段：README + ACCEPTANCE + PROBLEMS(P24–P33) + 4 份 EVIDENCE
docs/tickets/p2-test-automation/        P2 阶段：README（T1–T6 全落地）+ coverage-report-round1.md
docs/MANUAL-TESTING.md                  人工测试统一入口（结果记录在第 3 节回填表）
docs/tickets/m0..m6/                    各里程碑票据 + ACCEPTANCE + PROBLEMS
docs/tickets/m6/ACCEPTANCE.md           M6 验收包（含 kill 实例 drill 原始输出）
docs/tickets/v1-verification/           V 阶段：README（进度）+ 6 票据 + 4 份 EVIDENCE + PROBLEMS(P17–P21)
docs/perf/M6-capacity.md                容量报告（§2.4 真模型、§2.5 拐点、§2.6 P18、§2.7 真模型并发与限流标定）
docs/resume/MN-resume-draft.md          各里程碑/P1 简历草稿（含 P1-resume-draft.md）
skills/repo-map/SKILL.md                "改 X 先看哪"（含两跳示例）
apps/api/src/better_resume/
  settings/config.py                    全部设置（BR_* 前缀；凭据字段为空默认）
  llm_gateway/{resolver,registry,adapters/}  场景绑定 + 模型注册 + OpenAI 兼容/星云 adapter
  ai_resilience/{resilient,distributed}.py   单飞/熔断/舱壁/超时 + Redis 分布式单飞
  interview_engine/{locks,hot_state,report_service}.py  题级锁/热层/报告冻结
  jobs/queue.py + worker.py             Redis Stream 队列 + worker（心跳、重试、死信、接管）
  media/adapters/{xunfei_ast,qwen_asr,paraformer_rt,edge_tts,scripted}.py  语音适配器（paraformer_rt=实时，默认）
apps/api/scripts/                       real_model_smoke / fault_probe / load_test / media_smoke / v3_ws_probe / assembler_real_probe / make_fixture_audio / check_coverage_floors / fake_openai / export_openapi / extract_api_index
apps/api/tests/                         747 例；test_source_hygiene.py 拦语法警告与转义反引号
scripts/verify.sh                       单一验证入口（P2-T1；CI 与本地同一份命令）
scripts/compose_smoke.sh                部署面验收（含 P29 缓存头断言）
scripts/kill_instance_drill.sh          §12.4 硬验收
scripts/fault_injection_drill.sh        V6 浸泡/故障注入
compose.yaml + deploy/nginx.conf        部署最终形态
```
