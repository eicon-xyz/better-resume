# M6 待确认项（决策请拍板，我不自行决议）

| 编号 | 一句话 | 我的提议 |
| --- | --- | --- |
| Q1 | 部署面与 worker 范围 | 补齐 D07 最终形态（worker + nginx + 双 api 实例 + 非 root），worker 做**真实任务**：报告生成异步化 |
| Q2 | 分布式单飞范围 | 实现 Redis 版（SET NX + owner token + 轮询结果键 + 判死接管），进程内快路径保留，由 T8 验收真跑 |
| Q3 | 压测形态 | 自研 asyncio 脚本（p50/p95/p99、429、SSE 首帧、单飞命中）+ `docs/perf/` 报告，只写实测数字 |
| Q4 | skills 范围 | repo-map + 10 份模块 SKILL.md + 自动 API 索引（CI 漂移检查） |
| Q5 | kill 验收口径 | docker compose 双 api 实例 + nginx，脚本化 drill：kill 一个实例 → 另一实例接管并断言状态一致 |

---

## Q1 部署面与 worker

M0 起就写着"worker / nginx 留给后续里程碑"，M6 是它的截止日期，但 worker 必须有真实职责，
否则就是 D07 点名的"死代码"。

- **A（提议）**：`worker` 消费 Redis Stream 做**报告生成异步化**（`POST /finish` 入队即返回，
  worker 生成 LLM 总结后写回，前端轮询 `summary_pending`）；`nginx` 统一入口（SPA + /api + WS + SSE 不缓冲）；
  `api` 非 root 镜像并支持 `--scale api=2`。
- B：只加 nginx（前端容器 + 反代），worker 不做——省 1.5 会话，但 D07 的最终形态仍然缺一块，
  且"报告生成为什么要占住 API 进程"这个问题一直留着。
- C：worker 只做定时清理（过期热层/死信），不做队列——实现简单，但价值小、也没有异步语义可讲。

## Q2 分布式单飞

- **A（提议）**：实现 Redis 版（跨实例只调一次上游 + 结果回放 + 判死接管 + fencing），
  与 M3 的进程内实现**叠加**（本地优先、跨实例补齐）；`distributed` 开关默认关，但 T8 的验收在打开状态下跑，
  因此它不是死代码。
- B：只做分布式**锁**（题级锁），单飞保持进程内——省 1 会话，但"多实例下同一次答题仍会各调一次上游"
  这个最贵的问题没解决，M6 的标题（分布式单飞）也就名不副实。
- C：两者都做，但 `distributed` 默认**打开**——更"开箱即用"，代价是单机开发也要连 Redis 才能工作。

## Q3 压测形态

- **A（提议）**：自研脚本（复用我们自己的 SSE 客户端与错误分类），三组场景 + JSON 落盘 +
  `docs/perf/M6-capacity.md`（环境、数字、瓶颈、不确定项）。
- B：引 locust/k6（报告好看，但依赖重、且要重新实现鉴权与 SSE 语义）。
- C：不写压测，只写"容量说明"——最省，但 M6 的验收里明确有"压测脚本"。

## Q4 skills 范围

- **A（提议）**：repo-map + 模块 SKILL.md（不变量/陷阱/测试地图）+ 自动 API 索引（CI 漂移检查）。
- B：只做 repo-map + API 索引（省 0.5 会话，但"陷阱"这一层——我们真正踩过的坑——就散在 PROBLEMS 里）。
- C：不做 skills（M6 验收里明确有它）。

## Q5 kill 验收口径

- **A（提议）**：compose 双 api 实例 + nginx + 脚本化 drill（kill → 继续答题/restore/finish →
  断言与 kill 前一致 + 打印 kill→恢复耗时 + `X-Instance-Id` 证明换了实例）。
- B：进程级验收（两个 uvicorn + 同一 Redis，kill 一个进程）——省去镜像构建时间，
  但少了 nginx 摘除与容器语义这一段真实经历。

