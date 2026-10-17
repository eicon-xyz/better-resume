# T13 缓存对象自带写路径失效语义（建议 5）

Type: task
Status: resolved
Blocked by: 无
唯一写入路径: `apps/api/`（红线内：缓存对象（interview_engine 热层、llm_gateway 场景绑定缓存等）与对应用例）

## 五栏

- 范围：读 `apps/api/src/better_resume/interview_engine/`（热层缓存）、`llm_gateway/`（`SceneResolver` 类绑定缓存）、`pitfalls-report.md` P10（负缓存启发式 / 读缓存忘失效 / 进程内缓存跨副本漂移）。
- 唯一写入路径：`apps/api/` 内——上述缓存对象、其调用点、对应用例。
- 验收口径（原始输出贴进 T13-EVIDENCE.md）：
  1. 红演示：「写路径没失效 → 写后读到过期视图」的用例在旧实现上必须红；
  2. 改后：缓存对象 API 含失效语义（写路径触发失效），TTL 只是兜底；
  3. 进程内配置缓存带 TTL 或写路径失效（多副本下不允许只在本地失效）；`grep -rn "_bindings\|invalidate\|cache" apps/api/src/better_resume/llm_gateway apps/api/src/better_resume/interview_engine` 结果逐条说明归属；
  4. 全量 pytest 绿：cd apps/api && export PATH="$HOME/.local/bin:$PATH" UV_CACHE_DIR='/root/better resume/.cache/uv' BR_DATABASE_URL='postgresql+asyncpg://better_resume:better_resume@127.0.0.1:5433/better_resume' BR_REDIS_URL='redis://127.0.0.1:6379/0' && uv run pytest -q --junitxml=/tmp/t13.xml（读数看 junitxml，不抄固定值）。
- 红线：不改 HTTP/DB 面；不引依赖；不动 p14 与 docs；不 commit/push/开 PR。
- 不接受的自由度：不许只加 TTL 蒙混（写后读一致是对象不变量）；不许把失效逻辑留在调用方；不许为过测试改断言语义。

## 红绿纪律

先红后绿：过期视图用例先行，最小实现转绿。

## 意图复述与实现决定交代

开工先把 `## 意图复述`（三行）追加进本票证据文件 `T<N>-EVIDENCE.md`；收工追加 `## 实现决定交代`（三栏表：spec 未覆盖我自行拍定的决定 / 为什么这么拍 / 我明确没做的），没有写「无」，不许留空。
## Comments

- 出票方裁决（并发冲突，2026-10-17 12:4x）：① 写范围重叠（T12/T13 同碰 llm_gateway）由出票方拆票粒度太粗所致，责任在派活方；已无法热改在途子代理的范围，收口时由出票方核 resolver.py 同时含 T12 的 ConfigStatus 快照与 T13 的 bind()，缺谁补谁。② 并行 pytest 共用同一 Postgres 导致全量读数不可信（P07 共享状态类在我们自己的流程里复现）——各票只需如实记录定向读数与全量尝试的归因，**权威全量读数由出票方在三票落地后串行复跑**，不认领并行期间的红。③ T13 在 test_scene_resolver.py 留下的 bind() 红用例归 T13 二轮（bind() 落地）解决。 ④ T13 裁决：resolver.py 冲突面归 T12（此裁决送达失败——子代理不可寻址）；T13 的 interview_engine 侧与 llm_gateway 侧拆两轮，二轮补 _bindings 失效语义后才结题。
## Answer

写后读一致成为缓存对象/写路径的不变量：热层失效进三个写服务、绑定写路径收进 `SceneResolver.bind()`，HTTP 端点零失效语句；红→绿两用例 + 39 定向绿。

### 追记（出票方验收）

- 变异演示：删答题写路径失效调用 → `test_every_write_path_drops_the_warm_hot_view` 判红（「答题写路径没有失效热层」），恢复逐字节一致。
- `resolver.py` 双改动（ConfigStatus ×7 + bind()）俱在；写入路径 8 文件与自述一致。
- 全量读数漂移定性为共享库污染（PROBLEMS.md P15-1），非本票回归——静默窗口整文件 10/10 全绿；权威全量并入 T17（隔离库复跑）。
- http-06/13 的 audit 处理并入 T17（授权 fix_record + 重锚）；读路径写库缺陷立 P15-2/T19，不属本票。
