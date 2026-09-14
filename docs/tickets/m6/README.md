# M6 票据拆分提案（待确认）

> 依据：docs/DECISIONS.md（D07 部署最终形态与「不养默认关闭的死代码」/ D11 会话与 WS 票据 /
> D13 skills 知识库 / D17 双 job CI）+ 分析文档 §4.1.5（分布式单飞三段式：ACQUIRE_OR_JOIN、
> fencing token、心跳续租、结果回放）、§4.1.6（长会话运行态治理与置信度）、§9.1 资产#12（部署面：
> 健康检查+条件依赖+非 root+密钥 fail-fast）、§12.4（M6 里程碑）、§13.1（skills 仓库自描述层）。
> 状态：**提案，等你确认后动工**。

## 1. M6 验收（§12.4 原文）

> 分布式模式（Redis 单飞/锁）+ 压测脚本 + skills 知识库（学原项目）→ **kill 实例恢复面试会话不丢状态**

## 2. 范围边界

**做**：Redis 分布式锁（题级锁接缝的第二个实现）；Redis 分布式单飞（M3 那个 Protocol 的分布式实现，
含 owner token / 租约 / 结果回放，**被验收真跑而不是默认关闭**）；会话热态与跨实例恢复（含来源标记）；
worker 服务（Redis Stream 任务队列 + 一个真实长任务：报告生成异步化）；nginx 反代与双 api 实例
（D07 最终形态，非 root 镜像 + 健康检查 + 条件依赖）；压测脚本与容量报告；skills 知识库
（repo-map + 每模块 SKILL.md + 自动 API 索引 + CI 漂移检查）；kill 实例端到端验收。

**不做**：Kubernetes / 服务网格 / 多区域；第三家 AI 供应商；ASR 侧的多实例路由（M4 已定单通道）；
把 Postgres 换成分库分表；前端 SSR。

**纪律**：红-绿 TDD；只 mock 系统边界（Redis 用真实例或 fakeredis、时钟注入）；内部模块不 mock；
小步提交说 WHAT；**实现中的难题即时记入 PROBLEMS.md**；D07 的诚实原则——任何"分布式模式"的代码路径
都必须被 M6 的验收覆盖，不允许留下默认关闭、没人跑的分支。

## 3. blocking 图

```
T1 分布式锁 ──┬─> T3 热态与跨实例恢复 ──┐
              │                          │
T2 分布式单飞 ┴──────────────────────────┼─> T8 kill 实例端到端验收 ──> T9 验收/PR
T4 worker + 任务队列 ────────────────────┤
T5 nginx + 双实例 compose ───────────────┤
T6 压测脚本 + 容量报告 ──────────────────┤
T7 skills 知识库 ────────────────────────┘
```

| 票 | 标题 | blocking | 预估 |
| --- | --- | --- | --- |
| T1 | Redis 分布式锁（题级锁接缝的第二个实现，含 fencing + 续租） | M5 | 1 会话 |
| T2 | Redis 分布式单飞（owner token / 租约 / 结果回放，进程内快路径保留） | M5 | 1.5 会话 |
| T3 | 会话热态与跨实例恢复（Redis 快照 + 来源标记 + 失效） | T1 | 1 会话 |
| T4 | worker 服务 + Redis Stream 任务队列（报告生成异步化，幂等/重试/死信） | M5 | 1.5 会话 |
| T5 | nginx + 双 api 实例：compose 最终形态（非 root、健康检查、条件依赖、WS 代理） | T4 | 1 会话 |
| T6 | 压测脚本与容量报告（吞吐/SSE 并发/限流与熔断行为/单飞命中率） | T5 | 1 会话 |
| T7 | skills 知识库（repo-map + 模块 SKILL.md + API 索引脚本 + CI 漂移检查） | M5 | 1 会话 |
| T8 | kill 实例端到端验收（脚本：面试进行中杀实例 → 另一实例恢复一致） | T1 T2 T3 T5 | 1 会话 |
| T9 | M6 验收证据 + PROBLEMS 收口 + 简历草稿 + README + PR | 全部 | 0.5 会话 |

## 4. 与原方案的取舍

1. **诚实原则的落地方式**：D07 说"分布式单飞只留接口不写 Lua"，那是 M0 阶段防死代码的约束；
   M6 的正事就是把它变成**被验收覆盖**的实现（T8 的 kill 实例测试会在 `distributed=true` 下跑），
   而不是加一个默认关闭的分支。**不做完整 Lua ACQUIRE_OR_JOIN**：我们用"SET NX + owner token +
   短轮询结果键"实现同样的语义，代码量是旧项目的十分之一，且每一行都有测试。
2. **单飞的两层结构**：进程内单飞（M3，快路径）先命中，未命中再走 Redis 协调（M6）——
   旧项目是"分布式默认关、本地兜底"，我们是"本地优先、跨实例补齐"，两者叠加而不是二选一。
3. **worker 不做成空壳**：M0 起就写着"worker 留给后续里程碑"，M6 给它一个**真实任务**：
   `POST /finish` 的报告生成（LLM 总结）改为入队，避免长请求占住 API 进程；幂等键与状态查询端点
   一起做，否则就是一个没人用的队列。
4. **热态只做"恢复所需"**：旧项目 973+893 行的快照/再水化服务是反面教材（§9.2 巨型类）。
   我们只缓存 restore 视图与流程状态，带来源标记（`EXACT`/`DERIVED`），Postgres 仍是唯一真相。
5. **压测给数字不给感觉**：脚本输出 p50/p95/p99、错误率、限流拒绝数、单飞命中率与缓存命中；
   报告里**只写脚本实测的数字**，并注明环境（本机 WSL2、非 root 容器、单机）。
6. **skills 是仓库自描述层，不是文档堆积**（D13）：repo-map 负责"改 X 先看哪"、每个深模块一份
   SKILL.md 写"不变量 + 陷阱"、API 索引由脚本从 OpenAPI 生成并加 CI 漂移检查（学旧项目的
   `extract_api_index.py`，但我们的源是 openapi.json，天然不会过期）。

## 5. 环境事实（影响验收口径）

- **Docker 又可用**（daemon 可达，compose v5.3.1）：M6 的 compose 形态与 kill 实例验收可以真跑，
  不再需要"本地两个 uvicorn 进程"的替代方案。
- 本机原生 Postgres 5433 / Redis 6379 仍用于测试；compose 用 5432/6379 + 独立卷，
  两者互不干扰（compose 起停不影响本机测试）。
- 镜像构建需要拉取基础镜像与依赖：首次构建较慢（预估 3-6 分钟），记入验收耗时。

## 6. 待确认项

见 `OPEN-QUESTIONS.md`（5 项：部署/worker 范围、分布式单飞范围、压测形态、skills 范围、kill 验收口径）。


## 进度（执行中）

| 票 | 状态 | 证据 |
| --- | --- | --- |
| T1 分布式锁 | ✅ | tests/test_distributed_lock.py（10 例：互斥/不同题并行/有界等待/异常释放/取消/TTL 过期/续租/陈旧 owner 不误删/50 并发串行/memory 回归） |
| T2 分布式单飞 | ✅ | tests/test_distributed_flight.py（10 例：两实例只调一次/跨实例回放/0 TTL 不缓存/可缓存失败回放/可重试失败不缓存/接管/fencing 拒写/有界等待/scalar 往返/拒绝外部模块） |
| T3 会话热态与跨实例恢复 | ✅ | tests/test_hot_state.py（8 例）+ 写路径失效回归；drill 里 kill 前后 restore 视图逐字段相等 |
| T4 worker + 任务队列 | ✅ | tests/test_job_queue.py（7 例）+ tests/test_job_worker_api.py（3 例：冻结数字先返回、worker 补总结、重复 finish 不重复入队）+ tests/test_worker_loop.py（4 例：Redis 抖动不杀 worker） |
| T5 nginx + 双实例 compose | ✅ | docs/tickets/m6/T5-EVIDENCE.md（ALL CHECKS PASSED：REST/SSE 心跳+分片/WS 101/非 root/两实例轮询/worker 心跳）；tests/test_deploy_manifest.py（14 例） |
| T6 压测脚本 + 容量报告 | ✅ | apps/api/scripts/load_test.py + tests/test_load_test_script.py（6 例）+ docs/perf/M6-capacity.md（三组实测；真模型未跑，已如实标注） |
| T7 skills 知识库 | ✅ | skills/{repo-map,modules×10,api-index}/ + apps/api/scripts/extract_api_index.py --check（exit 0）+ tests/test_skills_index.py（39 例）+ CI 新增漂移步骤 |
| T8 kill 实例 drill | ✅ | scripts/kill_instance_drill.sh + apps/api/scripts/kill_instance_drill.py + tests/test_drill_prereqs.py（3 例）；输出见 ACCEPTANCE §1（kill→恢复 237 ms） |
| T9 验收 + PR | ✅ | docs/tickets/m6/ACCEPTANCE.md + PROBLEMS.md P0–P14 + docs/resume/M6-resume-draft.md + README |

**验收口径**：§12.4 的"kill 实例恢复面试会话不丢状态"由 `bash scripts/kill_instance_drill.sh` 一条命令复跑；
部署面由 `bash scripts/compose_smoke.sh` 复跑；容量数字由 `docs/perf/README.md` 里的命令复跑。
后端 648 例 / 前端 158 例全绿；未验证项集中在真机凭据与生产网络（见 ACCEPTANCE §6）。

**续做入口**：`git checkout main && git pull` → 读 `skills/repo-map/SKILL.md` 找模块入口 →
`uv run pytest -q`（648 例）与 `bash scripts/compose_smoke.sh`（需要 docker）应全绿。
