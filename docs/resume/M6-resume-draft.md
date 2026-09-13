# 简历草稿（M6 分布式 / 容量 / skills 里程碑）

> D14 硬规则：每个里程碑结束更新一次简历草稿。
> 口径原则：**只写跑通并可复跑的东西**；M6 的对外物 = 一条命令证明"kill 掉正在服务的 api 实例，
> 面试会话不丢状态"，以及一套可复跑的部署面 + 容量数字。真模型高并发未测（如实标注）。

## 1. 本阶段新增条目（有执行证据）

- **分布式单飞（跨实例只调一次上游）**：在 M3 的进程内单飞 Protocol 后面补上 Redis 实现 ——
  `SET NX PX` 抢 owner + owner token + 租约续租 + **先查结果再抢锁**（避免 owner 释放瞬间的"空档重跑"）
  + fencing 拒写（过期 owner 回来写结果会被拒）+ 结果回放（白名单模块编解码）。两实例并发同 key
  上游只调用 **1** 次（有测试与 HTTP 层证据）。
- **题级分布式锁**：题级锁接缝的第二个实现，SET NX + token 释放 + 续租，替换"进程内锁"后
  `--scale api=2` 下同一道题不会被两个实例同时评分。
- **会话热态与跨实例恢复**：restore 视图先读 Redis 热快照（带 `source=hot/derived` 来源标记），
  写路径（出题 / 答题 / finish）**主动失效**，Postgres 仍是唯一真相。
- **后台 worker（不是空壳）**：`POST /finish` 改为"冻结确定性报告 + 报告总结入队"，客户端立刻拿到
  数字、总结稍后由 worker 补；Redis Stream 消费组 + 幂等键去重 + 重试退避 + 死信流 +
  `XPENDING+XCLAIM` 崩溃接管（兼容 Redis 6.0，没有 XAUTOCLAIM）；worker 有心跳键与
  `--health` 自检，Redis 抖动不会杀死进程。
- **部署最终形态（D07）**：nginx 一个入口（SPA `try_files` + `/api` 反代、`proxy_buffering off`、
  WS `Upgrade`、300s 超时）→ `api` 可 `--scale`（无宿主机端口、共享 `uploads` 卷、非 root uid 999）→
  `worker` + `postgres` + `redis`；一次性 `migrate` 服务用
  `service_completed_successfully` 卡住 api/worker 启动；`X-Instance-Id` 响应头暴露服务实例。
- **一条命令的硬验收**：`bash scripts/kill_instance_drill.sh` —— 面试进行到一半
  `docker kill` 正在服务的实例，nginx 把后续请求交给另一个实例（实测 kill→恢复 **237 ms**），
  断言题号 / 已答数 / 分数 / 追问计数一致、同 `request_id` 重放不重复计费、报告数字等于冻结值、
  排队任务由 worker 完成。
- **容量报告而不是感觉**：自研 asyncio+httpx 压测脚本（mixed / chat-sse / answer-submit），
  输出 p50/p95/p99、RPS、错误率、429、SSE 首帧延迟与失败分类；实测 20 并发 mixed 41.7 rps、
  非流式 p50 17 ms、SSE 首帧里我们自己的增量约 30 ms（其余是假上游的固定延迟）。
- **仓库自描述层（skills）**：repo-map（改 X 先看哪）+ 10 份模块 SKILL.md（不变量 / 踩过的坑 /
  测试地图）+ **由脚本生成的 API 索引**（24 REST + 1 WS + 8 条前端路由）并接进 CI 漂移检查 ——
  人和 agent 都先读 skills 再动手。

## 2. 数字（可复核）

| 指标 | M3 | M4 | M5 | M6 |
| --- | --- | --- | --- | --- |
| 后端测试 | 415 | 473 | 528 | **645** |
| 前端测试 | 115 | 152 | 158 | 158（本阶段无前端改动） |
| 迁移 | 4 | 4 | 5 | 5 |
| compose 服务 | 3 | 3 | 3 | **6**（migrate / api×N / worker / nginx / postgres / redis） |
| 压测（20 并发 mixed，假上游） | — | — | — | 41.7 rps，p50 17 ms，p95 2.46 s，429=18/935 |
| kill 实例恢复 | — | — | — | **237 ms**（另一次 5.4 s，取决于 nginx 何时发现死上游） |
| skills 知识库 | — | — | — | repo-map + 10 模块 SKILL.md + 生成式 API 索引（39 例测试守漂移） |

## 3. 与旧项目资产的承接对照

| 旧项目资产 | 新承接物（M6 已落地） |
| --- | --- |
| 分布式单飞 6 段 Lua + fencing + 心跳（默认关闭） | `RedisFlight`：SET NX + owner token + 续租 + 结果回放 + fencing 拒写；**默认在 compose 下开启并被 kill 演练覆盖** |
| SessionSnapshot / RehydrateService（973+893 行巨型类） | 只缓存 restore 视图 + 来源标记；写路径失效；Postgres 唯一真相 |
| deploy compose（healthcheck + 条件依赖 + 非 root） | `migrate` 一次性服务 + 条件依赖 + 非 root + 共享卷 + nginx 变量 upstream（扩容即生效） |
| `extract_api_index.py`（旧项目手写索引） | 从 `openapi.json` + 前端路由**生成**索引，CI 漂移检查兜底 |
| 压测靠"感觉快" | 自研脚本 + 容量报告 + 8 条不确定项（含"答题场景被默认限流削峰"这条自我证伪） |

## 4. 下一里程碑要补的证据

- **真模型**：用真实 DeepSeek/星云跑 §2.4（容量报告已留空位）；真机凭据（讯飞 / 星云）与
  真实浏览器的人工 4 步清单仍欠着（M4/M5 遗留）。
- **多可用区 / Redis 集群 / 网络分区**：本轮只覆盖单机多进程；要做"Redis 主从切换时锁与单飞的行为"。
- **浸泡测试**：>10 分钟的稳定性（内存 / 连接 / Redis 内存增长），以及限流桶按真实流量标定。
