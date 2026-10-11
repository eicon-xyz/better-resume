# M6-T4 — worker 服务 + Redis Stream 任务队列（报告生成异步化）

- blocking：M5
- 纪律：先写失败测试（红），再实现（绿）；**队列必须有真实消费方，不做空壳服务**

## 目标

M0 起就写着"worker 留给后续里程碑"。M6 给它一个真实任务：**报告生成（LLM 总结）异步化** ——
`POST /finish` 立即返回"已入队"，worker 消费后写回报告，前端轮询/重试。
这样 API 进程不再被 20s 级的模型调用占住，也第一次有了真正的后台任务语义。

## 交付物

- `jobs/queue.py`：Redis Stream 封装（`XADD`/`XREADGROUP`/`XACK` + 消费者组 + 待处理重投）
  - 幂等：任务键 `jobs:dedupe:{kind}:{idempotency_key}`（`SET NX`）；重复入队返回既有 task_id
  - 重试：失败计数 + 指数退避（注入时钟）；超过 `max_attempts` 进死信流 `br:jobs:dead`
  - 可见性：任务状态 `queued|running|done|failed`（Redis Hash + TTL）
- `jobs/report_worker.py`：消费 `report.summary` 任务 → 调 ReportService 的总结路径 → 写回 + 状态更新
- `http/interview.py`：`POST /finish` 改为入队并返回 `{status:"queued", task_id}`；
  新增 `GET /api/v1/interview/sessions/{id}/report` 的轮询语义（已存在，返回 `summary_pending` 标记）
- `worker.py`（apps/api 内的独立入口）：启动消费者循环，优雅退出（`SIGTERM` 后处理完当前任务）
- 测试：`tests/test_job_queue.py` + `tests/test_report_worker.py`（≥14 例）

## 测试

| 用例 | 断言 |
| --- | --- |
| 入队/消费 | 入队一个任务 → 消费者处理 → 状态 done、结果落库 |
| 幂等 | 同 idempotency_key 入队两次 → 同一 task_id，只消费一次 |
| 失败重试 | 第一次抛错 → 重试（假时钟退避）→ 第二次成功 |
| 死信 | 超过 max_attempts → 进死信流，状态 failed（带最后一次错误） |
| 崩溃恢复 | 消费者未 ACK 就"崩溃"（不 ACK）→ 另一消费者用 XAUTOCLAIM 接管 |
| 状态查询 | `GET report` 在 queued/running 时返回 `summary_pending=true`，完成后返回总结 |
| finish 幂等 | 同一会话 finish 两次 → 只有一个任务（且报告只冻结一次） |
| 无 worker 时 | 不入队失败，业务仍可用（报告数字照常返回，summary 待生成） |
| 优雅退出 | 收到信号后处理完当前任务再退出（无半截任务） |

## 验收

| 命令 | 期望 |
| --- | --- |
| `uv run pytest -q tests/test_job_queue.py tests/test_report_worker.py` | 全绿 |
| compose | `docker compose up -d --wait` 后 worker 容器 healthy（心跳键） |

## 不做

- 不引 Celery/RQ/arq（D04 自研轻量编排的精神：Redis Stream 足够且能讲清）；
- 不做任务优先级/定时任务（只做"报告生成"这一类）；
- 不做多队列分片（单流 + 消费者组够用）。

