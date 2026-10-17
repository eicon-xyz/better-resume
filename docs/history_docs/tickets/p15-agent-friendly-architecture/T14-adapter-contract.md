# T14 适配器协议契约测试（建议 6，含建议 4 的自检口径）

Type: task
Status: resolved
Blocked by: 无
唯一写入路径: `apps/api/`（红线内：apps/api/tests/media 下的契约测试文件、为过契约所需的 adapter 最小修正）

## 五栏

- 范围：读 `apps/api/src/better_resume/media/`（TranscriptionChannel 协议与 assembler）、`media/adapters/`（scripted 等）、`apps/api/tests/media/`、`pitfalls-report.md` P11（wait() 违反协议 / 成功路径不关 WS / 连接参数吃库默认值）。
- 唯一写入路径：`apps/api/` 内——新契约测试文件与被契约点名的 adapter 最小修正。
- 验收口径（原始输出贴进 T14-EVIDENCE.md）：
  1. 契约套件对 scripted 适配器全绿，断言至少三条：`wait()` 在 `stop()` 之前不得返回、成功路径显式 `close(1000)`（WS 类适配器；无凭据的真适配器跳过并写明）、连接参数（open/close 超时、proxy）不得吃库默认值；
  2. 套件自证：用例内嵌故意违反各条契约的坏 fake 适配器，必须被判红（每条契约至少一个坏 fake）；
  3. 全量 pytest 绿：cd apps/api && export PATH="$HOME/.local/bin:$PATH" UV_CACHE_DIR='/root/better resume/.cache/uv' BR_DATABASE_URL='postgresql+asyncpg://better_resume:better_resume@127.0.0.1:5433/better_resume' BR_REDIS_URL='redis://127.0.0.1:6379/0' && uv run pytest -q --junitxml=/tmp/t14.xml（读数看 junitxml，不抄固定值）。
- 红线：不改适配器对外行为（仅为满足契约的最小修正，逐条记录在实现决定交代）；不引依赖；不动 p14 与 docs；不 commit/push/开 PR。
- 不接受的自由度：不许 mock 内部模块冒充契约（断言走公开行为）；不许「跑通即可」式断言；坏 fake 不许只覆盖一条契约。

## 红绿纪律

先红后绿：坏 fake 先证明套件会红，再对真实适配器转绿。

## 意图复述与实现决定交代

开工先把 `## 意图复述`（三行）追加进本票证据文件 `T<N>-EVIDENCE.md`；收工追加 `## 实现决定交代`（三栏表：spec 未覆盖我自行拍定的决定 / 为什么这么拍 / 我明确没做的），没有写「无」，不许留空。
## Comments

- 出票方裁决（并发冲突，2026-10-17 12:4x）：① 写范围重叠（T12/T13 同碰 llm_gateway）由出票方拆票粒度太粗所致，责任在派活方；已无法热改在途子代理的范围，收口时由出票方核 resolver.py 同时含 T12 的 ConfigStatus 快照与 T13 的 bind()，缺谁补谁。② 并行 pytest 共用同一 Postgres 导致全量读数不可信（P07 共享状态类在我们自己的流程里复现）——各票只需如实记录定向读数与全量尝试的归因，**权威全量读数由出票方在三票落地后串行复跑**，不认领并行期间的红。③ T13 在 test_scene_resolver.py 留下的 bind() 红用例归 T13 二轮（bind() 落地）解决。
## Answer

契约套件 8 例（5 绿主体 + 3 坏 fake 自证红）落地；paraformer_rt 收尾 close(1000) 最小修正；tests/media 73 全绿；出票方变异演示：close(1000) 拔回 close() → test_realtime_asr_closes_the_vendor_socket_with_1000 判红，恢复逐字节一致。

## Comments

- 出票方验收：契约套件与 tests/media 复跑 exit 0；写入路径恰 3 文件；变异演示红→绿→恢复。
- 全量 pytest 红灯归因认可（p14 在飞 + T12/T13 并发改动面），权威全量读数由出票方在 T12/T13/T17 落定后串行复跑。
- xunfei AST 无注入缝导致契约 2/3 未覆盖——记入评审清单，等价于建议 6 的已知残余。
