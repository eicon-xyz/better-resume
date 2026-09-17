# P1 阶段验收包：实时 ASR / 真模型容量 / 阿里 API 补验 / 生产形态演练

- 阶段：P1（`docs/tickets/p1-post-v/README.md`）；分支 `p1/realtime-asr`（基于 main = `9679e14`；
  历史抹除前的旧哈希 `e202eab` 已不存在，见 `docs/HANDOFF.md` §1）
- 环境：WSL2 Ubuntu 22.04 / Docker Desktop（compose：nginx + 2×api + worker + postgres + redis）
- 结论：**P1-A / P1-B / P1-C / P1-D 全部完成，已于 2026-09-17 通过用户正式验收**（见 §7）。过程中发现并
  修掉 **3 个真 bug**（P24/P26 与其 P25/P27 两个证据工具缺陷），全部先红-绿补测试再修。
- 真机花费：**~177 次调用**（P1-A ~10、P1-B 164、P1-C 2、P1-D 0——浸泡零供应商调用），在约定封顶内。

## 1. 逐票结果与证据

| 票 | 结论 | 关键数字 | 证据 |
| --- | --- | --- | --- |
| **P1-A** 实时 ASR（Paraformer） | ✅ | 端到端穿 nginx：首增量 **0.56s**、增量随说话到达；**松手→final 1.1s**（修 P24 前 10.1s）；关闭码 1000 | `P1-A-EVIDENCE.md` |
| **P1-B** 真模型并发 + 限流标定 | ✅ | **24 并发真流**（V2 的 6 倍）0 供应商 429/5xx；标定 `ai_call 6→2`、`answer 8→2`（红-绿 + 实证 c=16→8 ok+8 rl） | `P1-B-EVIDENCE.md`、`docs/perf/M6-capacity.md` §2.7 |
| **P1-C** 以阿里 API 补验（原讯飞/星云） | ✅（一处待 app_id） | 多句真机 20 replace + 3 archive + final（含供应商自我纠错）；句池真机包回放**提交语义 PASS**、边界 26 段 vs 3 句已记录 | `P1-C-EVIDENCE.md` |
| **P1-D** 生产形态演练 | ✅ | 分区：healthz 9/9、认证 503+`retry-after`、恢复 0.2–2.2s；切换：91/92 ok、恢复 **109ms**、旧会话存活、worker 存活；浸泡 **120 波/3600 请求/0 失败**、非会话键 +0、PG 连接 +0、api 内存 +0.5MB/h | `P1-D-EVIDENCE.md` |

## 2. 发现并修复的真 bug

| 编号 | 一句话 | 修法 | 测试 / 真机复验 |
| --- | --- | --- | --- |
| **P24** | `websockets` 默认 `close_timeout=10s`：供应商不回关闭帧 → **松手后 10.1s 才出 final** | 显式 `close_timeout=1` + 尾部预算 2s（预算耗尽仍发 final） | 3 个新单测；端到端 15.63s → **6.62s** |
| **P26** | **Redis 主从切换时 worker exit 1**：心跳写位于 `serve()` 兜底 try 之外，`TimeoutError` 逃出循环；无重启策略 → 后台任务永久停摆 | 心跳移进兜底 try（记录 + 退避） | 红 `assert 1 >= 2` → 绿；真机复跑 `worker_health=healthy` + 7 条降级日志 |
| **P25** | 端到端探针"发完才收"→ 增量时序塌缩，差点误判正确实现 | 探针改并发 reader（边发边收） | 修复前后输出对照（P1-A-EVIDENCE §3 c/d） |
| **P27** | 演练探针自身缺陷：分区前未登录采到 401（误判 P17）；采样无 try/except、恢复无 `finally` → 崩过一次并把栈留在断网态 | 先建会话、采样包 try/except、恢复放 `finally` | 原始 curl 对照 503 + `retry-after: 5` |

## 3. 自动化回归（收口时）

| 项 | 结果 |
| --- | --- |
| 后端 | **695 passed / 0 failed / 0 skipped**（junitxml 实读；M6 收口 648 → V 收口 678 → P1 收口 695） |
| 前端 | **161 passed (23 files)** |
| 静态检查 | ruff format/check 干净（本阶段所有改动文件） |
| 契约三件套 | 无 REST 模型变更：`export_openapi.py` 复跑后无 diff、`extract_api_index.py --check` 通过 |
| 演练脚本 | `fault_injection_drill.sh` 现含 5 个故障实验 + 浸泡，语法与纯逻辑测试通过 |

**P2 收口 + 验收当窗复核**（2026-09-17，本机 `bash scripts/verify.sh --layer all`，退出码 0）：

| 项 | 结果 |
| --- | --- |
| 后端 | **744 passed**（含 P2 新增的脚本回归与覆盖率插桩） |
| 前端 | **173 passed (24 files)** |
| 脚本回归 | **22 passed**（`test_fault_probe` / `test_load_test_script` / `test_real_model_smoke_script` / `test_verify_script`） |
| 深模块覆盖率底线 | **7/7 通过**（最低 `resume_parser` 93.2%、`media` 93.7%，底线 90%；`check_coverage_floors.py`） |
| 证据 | `var/evidence/20260917T141212Z-all/` |

## 4. 未验证项（诚实清单）

1. **讯飞 AST / 星云工作流真机**：无凭据，未验证（P1-C 用阿里实时 ASR 覆盖同类能力，非同一协议）；
   星云的阿里等价物（百炼应用调用）**等用户提供 app_id**。
2. **真实浏览器手测（P1-A）**：WS 协议层已验（穿 nginx），浏览器麦克风真实节奏待用户手测。
3. **供应商 429 真机表现**：177 次真调用一次未触发，退避/重试路径仍是纸面推演。
4. **>24 并发 / 自动 failover / 多可用区**：未测；应用是单 `BR_REDIS_URL`，自动切换需代码改动（另提案）。
5. **浏览器矩阵**（Safari/Firefox/蓝牙）延续 V 阶段未验证。

## 5. 与提案的偏差

| 偏差 | 原因 | 影响 |
| --- | --- | --- |
| P1-C 从"讯飞 AST / 星云真机"改为"用阿里 API 验证" | 用户指令（2026-09-15）：无讯飞/星云凭据 | 同类能力有真机证据；原生 adapter 仍标未验证 |
| 新增 P24/P26 两个业务修复与 P25/P27 两个工具修复 | 验证与演练过程暴露的真实契约错误 | 每项先红-绿；未改变既有 API 契约 |
| P1-B 增加"多身份并行"打供应商（提案只写单身份分级） | 单身份被我们自己的桶整形，压不到供应商 | 真机并发从 c≤4 提升到 24；花费仍在封顶内 |
| P1-D 新增两个演练场景 + 60 分钟浸泡 | 提案要求；浸泡期间不注入故障 | `fault_injection_drill.sh` 5 步全绿 |

## 6. 怎么复跑（最短路径）

```bash
cd '/root/better resume' && export PATH="$HOME/.local/bin:$PATH"
cd apps/api && export BR_DATABASE_URL='postgresql+asyncpg://better_resume:better_resume@127.0.0.1:5433/better_resume' BR_REDIS_URL='redis://127.0.0.1:6379/0'
uv run pytest -q --junitxml=/tmp/x.xml                      # 695
uv run python scripts/v3_ws_probe.py --realtime             # P1-A 端到端（栈在跑）
uv run python scripts/load_test.py --scenario chat-sse --concurrency 16 --requests 16 --tag repro   # P1-B 天花板
uv run python scripts/media_smoke.py --paraformer-rt-real --wav ../../data/audio/p1c-multi-sentence-16k.wav  # P1-C
uv run python scripts/assembler_real_probe.py               # P1-C 句池（1 次真调用）
uv run python -m scripts.fault_probe fault --scenario redis-partition --seconds 20   # P1-D
uv run python -m scripts.fault_probe fault --scenario redis-failover  --seconds 20   # P1-D
pnpm -C apps/web test --run                                 # 161
```

## 7. 人工验收结论

**通过（用户验收，2026-09-17）**：

- **浏览器手测（P1-A）**：第 3 轮通过——实时转写边说边出字、录音中手写内容原位保留；过程修掉 P28（页面级
  合并层）/ P29（部署缓存头）/ P30（chat Composer 内部第三层合并），三轮记录见 `docs/MANUAL-TESTING.md` §5。
- **自动化基线**（验收当窗本机复核，`bash scripts/verify.sh --layer all` 退出码 0）：后端 **744 passed**、
  前端 **173 passed (24 files)**、脚本回归 **22 passed**；深模块覆盖率底线 **7/7**；
  证据 `var/evidence/20260917T141212Z-all/`。
- **验收范围**：P1 四票（P1-A 实时 ASR / P1-B 真模型容量与限流标定 / P1-C 阿里 API 补验 / P1-D 生产形态演练）
  + P2 六票（T1–T6 测试自动化）**整体通过**；未验证项与 §4 诚实清单一致（讯飞/星云真机、供应商 429、
  >24 并发与自动 failover、浏览器矩阵仍挂着，不因验收而消失）。
- **结论**：进入 PR（`p1/realtime-asr` → `main`）；合并需用户再次点头。

### 7.1 验收后 CI 暴露的修复（2026-09-17，PR #8 首跑）

验收当窗的"本地全绿"掩盖了 3 个**只有干净 checkout / CI 才看得见**的缺陷（台账 `PROBLEMS.md` P31–P33）。
PR #8 首跑：frontend ✅ 41s；backend ❌ 1m37s（unit 步 743 passed / 1 failed）。逐条红-绿修完：

| 编号 | 缺陷 | 红（先演示） | 绿 |
| --- | --- | --- | --- |
| **P31** | `verify.sh --layer all` 只展开 unit+scripts，而 `--list` 与 AGENTS.md 都写"all = unit + contract + scripts" → 本地"收口"永远不跑 contract（M6 P16 模式复活） | 新增展开漂移测试，列出被静默跳过的 **9 条** contract 命令 | `all` 展开 12 条命令；`test_verify_script.py` 4 passed |
| **P32** | `test_fixture_audio_check_passes_on_the_pinned_file` 断言本机 `data/audio/*.wav` 存在，但 `data/` 是 gitignored（Q3）→ 干净 checkout 必红 | real 层缺 fixture / 字节漂移时只报 "needs the compose stack"（该拒绝的位置不对） | real 层新增 fixture 预检（缺文件/漂移都在**花钱之前** exit 2）；单测改 hermetic（tmp 路径） |
| **P33** | `apps/api/scripts/fault_probe.py`（P1-D 提交 2f394be）过不了全仓 `ruff format --check .`；P1 收口只查了"改动文件" | `--layer contract` exit 1 | `--layer contract` **9/9 绿**（纯格式） |

修复后本机复核：`bash scripts/verify.sh --layer all` = **12 条命令全绿**（后端 **747** / 前端 **173 (24 files)** /
contract 9/9 / 脚本 **23**），证据 `var/evidence/20260917T142720Z-all/`。

