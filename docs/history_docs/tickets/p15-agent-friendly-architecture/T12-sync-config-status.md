# T12 配置状态改为同步快照 API（建议 3）

Type: task
Status: resolved
Blocked by: 无
唯一写入路径: `apps/api/`（红线内：llm_gateway 的配置判断缝、其调用点与对应用例）

## 五栏

- 范围：读 `apps/api/src/better_resume/llm_gateway/`（场景绑定 resolver / factory / `is_configured` 调用面）、`pitfalls-report.md` P01/P11、README 建议 3 与原型结论 A（ruff 对协程布尔零告警，故归架构层）。动前先 `grep -rn "is_configured\|configured" apps/api/src apps/api/tests` 清点全部调用点。
- 唯一写入路径：`apps/api/` 内——llm_gateway 配置判断缝、被波及的调用点、对应用例；其他模块（http/db/media 等）不动。
- 验收口径（原始输出贴进 T12-EVIDENCE.md）：
  1. 红演示：按历史 bug 形态写失败用例（异步判断被跳过 → 守卫形同虚设），改动前必须红；
  2. 改后配置状态判断是同步值 API（快照/布尔），调用面不存在「await 才有值」的布尔判断；
  3. `grep -rn "is_configured" apps/api/src` 剩余命中逐条有说明（改名或即快照 API）；
  4. 全量 pytest 绿：cd apps/api && export PATH="$HOME/.local/bin:$PATH" UV_CACHE_DIR='/root/better resume/.cache/uv' BR_DATABASE_URL='postgresql+asyncpg://better_resume:better_resume@127.0.0.1:5433/better_resume' BR_REDIS_URL='redis://127.0.0.1:6379/0' && uv run pytest -q --junitxml=/tmp/t12.xml（读数看 junitxml，不抄固定值）。
- 红线：不改 HTTP/DB 面；不引依赖；测试只 mock 系统边界（LLM/时钟/Redis/讯飞/浏览器音频/IPC）；不动 p14 与 docs；不 commit/push/开 PR。
- 不接受的自由度：不许「留 async 布尔判断 + 文档提醒」（第 3 层已被原型证明会复发）；不许新增第二套配置判断；不许改公开场景绑定语义——行为只收窄到「判断真的会执行」。

## 红绿纪律

先红后绿：失败用例先行，改最小实现转绿；用例只写在本票点名的缝上。

## 意图复述与实现决定交代

开工先把 `## 意图复述`（三行）追加进本票证据文件 `T<N>-EVIDENCE.md`；收工追加 `## 实现决定交代`（三栏表：spec 未覆盖我自行拍定的决定 / 为什么这么拍 / 我明确没做的），没有写「无」，不许留空。
## Comments

- 出票方裁决（并发冲突，2026-10-17 12:4x）：① 写范围重叠（T12/T13 同碰 llm_gateway）由出票方拆票粒度太粗所致，责任在派活方；已无法热改在途子代理的范围，收口时由出票方核 resolver.py 同时含 T12 的 ConfigStatus 快照与 T13 的 bind()，缺谁补谁。② 并行 pytest 共用同一 Postgres 导致全量读数不可信（P07 共享状态类在我们自己的流程里复现）——各票只需如实记录定向读数与全量尝试的归因，**权威全量读数由出票方在三票落地后串行复跑**，不认领并行期间的红。③ T13 在 test_scene_resolver.py 留下的 bind() 红用例归 T13 二轮（bind() 落地）解决。
## Answer

配置判断收窄为一次取回的 `ConfigStatus` 值快照（`if not status.configured`），旧 async 布尔钩子删除、协议违约响亮失败；红→绿两用例钉住，隔离库全量 1009/1（唯一红=审计引证，归 T17）。

### 追记（出票方验收）

- 变异演示：resolve 守卫恒不触发 → `test_unconfigured_adapter_is_reported_not_hidden` 与 `test_config_status_snapshot_carries_the_missing_credential` 判红，恢复逐字节一致。
- 定向集复跑 exit 0、failures=0（首跑路径笔误 exit 4，属出票方读数问题）。
- 写入路径 8 文件与自述一致；resolver.py 与 T13 bind() 合并完整。
- SKILL.md 的 is_configured 语义过期 → P15-6，并入 T18 的 skills 写入面。
