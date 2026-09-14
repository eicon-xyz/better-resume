# V6 — 浸泡测试 + 故障注入（不需要凭据，本机可做）

- blocking：无
- 纪律：故障注入只打**基础设施**（Redis/worker/nginx），不改业务代码；每个实验都要有明确的观察指标

## 目标

验证 M6 的分布式组件在"跑久了"和"东西坏了"时的行为，而不是只在健康路径上一次通过：

1. **浸泡**：假上游 mixed 场景连续压 15–30 分钟，观察内存/连接/Redis 键/报告任务积压是否单调增长；
2. **Redis 暂停（docker pause redis 20s）**：锁与单飞怎么表现？worker 是否按 P9 的设计继续活着？
   恢复后是否自愈（心跳、队列、回放）？
3. **Redis 重启（kill 后由 compose 拉起）**：会话（Redis 会话存储）如何降级？——预期：已登录用户掉线，
   需重新登录；这条要在文档里明说，不许含糊；
4. **worker kill**：正在生成总结的任务是否被重新投递（XPENDING+XCLAIM）并最终完成？
5. **nginx 摘除副本**：确认失败副本在 `valid=10s` 窗口内被换掉（V6 顺带复测 drill 的 1s 探针数字）。

## 交付物

- `scripts/fault_injection_drill.sh` + `apps/api/scripts/fault_probe.py`：
  - `--pause-redis SECONDS` / `--restart-redis` / `--kill-worker` / `--kill-api`
  - 每个实验打印：注入时刻、期间错误分类计数（429/5xx/timeout）、恢复时刻、恢复后首个成功请求耗时
- `docs/tickets/v1-verification/V6-EVIDENCE.md`：五个实验的原始输出 + 观察指标表格
- 测试：`tests/test_fault_probe.py`（无 docker 时 exit 2；解析逻辑用例）
- `PROBLEMS.md`：把新发现的坑记进去（预计：会话存储在 Redis 的降级语义、worker 停顿时的任务延迟）

## 测试与验收

| 用例 | 断言 |
| --- | --- |
| 浸泡 | 30 分钟内 `error_rate` 不单调上升；内存/连接数增长有上限说明；Redis 键数不无限增长 |
| Redis pause 20s | 期间请求以 5xx/timeout 计并**分类正确**；worker 进程存活；恢复后 5s 内首个 2xx |
| Redis 重启 | 会话失效被如实记录（用户需重新登录），不出现"假装还登录着" |
| worker kill | 任务在 ~60s 内被重新投递并完成；`br:jobs:dead` 不增长 |
| 脚本 | 无 docker 时 exit 2 且有可读提示 |

## 不做

- 不做网络分区（tc netem）与多节点故障（本机单节点）；不做 chaos 平台化。

## 预估

1 会话（含 30 分钟浸泡，可后台跑）。
