# P2 提案：测试自动化方案（分层 · 单一入口 · 可调度的重型验证）

> 依据：`AGENTS.md`（契约三件套、本地必须镜像 CI）、M6 P16（"本地全绿、CI 直接红"）、
> P25/P27（证据工具自身要先被校准）、P1 收口时的实测盘点。
> 状态：**提案，待你确认后动工**（本文件只出方案，未改任何代码/流程）。

## 1. 现状盘点（实测，不是印象）

| 层 | 内容 | 现在在哪跑 | 触发方式 | 缺口 |
| --- | --- | --- | --- | --- |
| **L0 单元/组件** | pytest **695** + vitest **161** | CI 双 job | push / PR | 无覆盖率度量 |
| **L1 契约/进程内集成** | 假上游（`fake_openai`）、假 WS 服务端、TestClient、契约三件套的 `--check`（openapi / api-index / gen:api） | CI | push / PR | 契约命令散落在 README/票据/CI 三处，本地靠"记得跑" |
| **L2 部署面** | `compose_smoke.sh`、`kill_instance_drill.sh` | **手工**（本机 docker） | 想起来才跑 | 无自动触发；输出不留档 |
| **L3 故障/浸泡** | `fault_injection_drill.sh`（5 实验 + 2/20 分钟浸泡）、`redis-partition`、`redis-failover`、60 分钟浸泡 | **手工** | 阶段收口时 | 同上；**回归无人守护**（P26 就是这么被手工演练抓到的） |
| **L4 真机** | `real_model_smoke`、`media_smoke`（真 ASR）、`v3_ws_probe`、`assembler_real_probe`、`load_test`（真模型） | **手工** | 阶段收口时 | 花费无守卫；**样本音频未入库**（`data/audio/` 未跟踪 → 别人复跑不了） |
| **L5 脚本自身回归** | 脚本 3437 行 Python + 296 行 shell；**只有 3 个脚本有测试**（`test_fault_probe` / `test_load_test_script` / `test_real_model_smoke_script`） | CI（那 3 个） | push / PR | 11 个脚本零测试（P1 新增的 `media_smoke` / `assembler_real_probe` / `v3_ws_probe` 都在其中） |

CI 现状（`.github/workflows/ci.yml`）：仅 push/PR 触发；无 `schedule`；无 artifacts 上传；无覆盖率。

## 2. 目标（可验收的成功标准）

1. **一套入口**：`scripts/verify.sh --layer unit|contract|deploy|fault|real|all`，**本地与 CI 调用同一份命令**
   （从根因上消灭"本地绿、CI 红"）。
2. **能自动跑的重型层真的自动跑**：deploy / fault 进 nightly；浸泡进 weekly；**真机层永不进 CI**（凭据 + 花费）。
3. **真机层有预算守卫**：调用计数 + 封顶，超限即停并落证据；缺凭据时**明确失败**而不是静默跳过。
4. **证据留档**：每次运行的 junit / 日志 / JSON 收进 `var/evidence/<timestamp>/`；CI 上传 artifacts。
5. **脚本自身有回归**：每个脚本至少两条契约——纯逻辑、以及"无 docker/无凭据时必须拒绝假装跑过"。
6. **覆盖率可见**：先度量、后设闸；只给深模块设 per-module 底线，不追全局百分比。
7. **flake 诚实**：不自动重试掩盖、不静默 quarantine；不稳定就是缺陷。

## 3. 分层设计

| 层 | 命令（单一事实源） | 在哪跑 | 触发 | 时长预算 |
| --- | --- | --- | --- | --- |
| L0 | `verify.sh --layer unit` → `pytest -m "not docker and not real"` + `vitest run` | 本机 / CI | push、PR | ≤ 3 min |
| L1 | `verify.sh --layer contract` → ruff check/format、eslint、tsc、alembic check、契约三件套 `--check` | 本机 / CI | push、PR | ≤ 4 min |
| L2 | `verify.sh --layer deploy` → compose_smoke + kill_instance_drill | CI（nightly）/ 本机 | schedule、手动 | ≤ 12 min |
| L3 | `verify.sh --layer fault` → 5 个故障实验 + partition/failover + 20 min 浸泡 | CI（nightly）/ 本机 | schedule、手动 | ≤ 35 min |
| L3b | `verify.sh --layer soak` → 60 min 浸泡（**零供应商调用**） | CI（weekly）/ 本机 | schedule、手动 | 60 min |
| L4 | `verify.sh --layer real` → 真机套件 + 预算守卫（读 `.env` 的 `BR_REAL_CALL_BUDGET`，默认 200） | **本机 only** | 手动、阶段收口清单 | 花费封顶 |
| L5 | `verify.sh --layer scripts` → 脚本回归测试 | 本机 / CI | push、PR | ≤ 1 min |

## 4. 票据拆分

| 票 | 标题 | 交付物 | 测试 / 验收 | 预估 |
| --- | --- | --- | --- | --- |
| **T1** | `scripts/verify.sh` 单一入口 | 分层入口脚本 + 证据目录约定 + CI 两个 job 改调它 | 同一命令本机与 CI 各跑一次，产物结构一致；`--list` 可打印层命令 | 0.5 会话 |
| **T2** | pytest markers 分层 | `unit` / `docker` / `real` 标记 + `--strict-markers` + 默认排除重型 | 误用标记会失败；`-m` 选择生效 | 0.3 会话 |
| **T3** | nightly / weekly workflow | `schedule` + `workflow_dispatch` + artifacts 上传 + 失败摘要 | 手动 dispatch 跑通一次并下载到产物 | 0.5 会话 |
| **T4** | 真机套件 + 预算守卫 | `verify.sh --layer real` + 调用计数 + 证据落盘 + 缺凭据即失败 | 计数器与真机日志一致；超预算非零退出 | 0.5 会话 |
| **T5** | 脚本回归补齐（11 个） | 每个脚本 ≥2 条契约测试（纯逻辑 + 拒绝假装） | 脚本层覆盖率 3/14 → 14/14 | 1.0 会话 |
| **T6** | 覆盖率度量 | pytest-cov + vitest `--coverage`；报告先行，深模块底线后设 | 报告在证据目录；阈值只对深模块 | 0.5 会话 |

**依赖**：T2 先于 T1/T5；T1 先于 T3/T4；T6 独立。

## 5. 关键设计决策（取舍，需你点头）

- **D1 单一入口优先于"CI 里再抄一遍命令"**：verify.sh 是唯一事实源，CI 只调用它——这是 M6 P16 的根治。
- **D2 重型层放 GitHub Actions nightly**：ubuntu runner 自带 docker，L2/L3 可跑；**私有仓库会消耗 Actions 分钟数**（见 Q1）。
- **D3 真机层永不进 CI**：凭据只在本机 `.env`；改为"阶段收口必跑清单 + 预算守卫"。
- **D4 不自动重试**：flake 必须被修或被显式标注，不允许 retry 掩盖。
- **D5 样本音频**：入库（约 400 KB × 2）或改成"脚本生成 + sha256 校验"（见 Q3）。
- **D6 覆盖率只设深模块底线**（`ai_resilience` / `interview_engine` / `media` / `identity` / `jobs`），不设全局百分比——避免为数字写垃圾测试。

## 6. 不做

- 不引第三方测试平台（Codecov / Allure / SonarQube）、不做 mutation testing；
- 不做浏览器矩阵自动化（Playwright 若要，另开提案——P1 的浏览器手测仍归人工）；
- 不把真机/浸泡放进 PR 门禁（PR 必须快）；
- 不做 CI 缓存调优（沿用现有 uv / pnpm 缓存）；
- 不为覆盖率补无意义断言。

## 7. 需要你决定

| # | 问题 | 影响 |
| --- | --- | --- |
| Q1 | nightly 频率？仓库是私有还是公开（私有=消耗 Actions 分钟数）？ | L2/L3 是否上云定时 |
| Q2 | 60 分钟浸泡：weekly 定时，还是只保留手动？ | 分钟成本 vs 长跑回归 |
| Q3 | 样本音频：入库，还是"生成 + 校验和"？ | 真机可复现性 |
| Q4 | 覆盖率：先只报告，还是直接给深模块设底线？ | T6 的范围 |
| Q5 | 真机预算：单次上限（默认 200 次）与"阶段收口必跑"清单是否强制？ | L4 的纪律强度 |

## 8. 验收口径（方案本身的）

1. `scripts/verify.sh --layer all` 在本机一次跑通，且**每一层都产出结构一致的证据**（junit + 日志 + JSON）；
2. CI 的 nightly 手动 dispatch 跑通一次并可从 artifacts 下载证据；
3. 真机套件在预算内跑完；**超预算或缺凭据时明确失败**（不是静默跳过）；
4. 脚本层测试从 3/14 提升到 14/14（每个脚本至少两条契约）；
5. 连续 3 次 nightly 全绿；若失败，证据里能直接看到是哪一层、哪条命令、原始输出。

## 9. 预估

T1–T6 合计 **约 3–3.5 个会话**；其中 T3（云上定时）需要你先回答 Q1。
