# M6-T8 — kill 实例端到端验收（§12.4 的硬验收）

- blocking：M6-T1 T2 T3 T5
- 纪律：**脚本化、可复跑**；证据是命令输出，不是叙述

## 目标

M6 的验收原话是「kill 实例恢复面试会话不丢状态」。本票把它变成一条可复跑的脚本：
起栈（nginx + api×2 + worker + postgres + redis）→ 真实面试流程走到一半 →
`docker kill` 掉正在服务该会话的 api 实例 → 经 nginx 的后续请求由另一实例接管 →
断言题号/已答数/分数/追问计数/报告全部一致。

## 交付物

- `scripts/kill_instance_drill.sh` + `scripts/kill_instance_drill.py`：
  1. 起栈（`docker compose up -d --wait --scale api=2`）
  2. 造数据：登录 → 建会话 → 上传简历 → 出题（记录实例 id，用 `X-Instance-Id` 响应头暴露）
  3. 答题 1~2 题（其中一题走单飞 + 题级锁路径）
  4. `docker kill` 该实例 → 等 nginx 摘除（健康检查失败窗口）
  5. 继续答题 / restore / finish / report：断言与 kill 前一致（题号、已答、分数、追问计数、
     报告数字 = 冻结值）
  6. 打印：kill 前后两次响应摘要 + Redis 键计数（单飞结果键、锁状态、热层键）
- `http/middleware`（或现有 request-id 中间件旁）：加 `X-Instance-Id` 响应头（`HOSTNAME` 或随机实例 id），
  用于证明"请求落到了另一个实例"
- 测试：`tests/test_instance_header.py`（≥3 例）+ 脚本自身在无 Docker 时的明确跳过/失败语义
- 验收文档章节：把 drill 输出贴进 M6 ACCEPTANCE，并注明 kill 到恢复的耗时

## 测试

| 用例 | 断言 |
| --- | --- |
| 实例头 | 每个响应都带 `X-Instance-Id`；两个进程的值不同 |
| drill 前置 | 无 Docker 时脚本退出码 2 且提示"需要 docker"（不是静默成功） |
| 会话一致 | kill 前后 restore 视图的结构化 diff 为空（排除 `source: hot/derived`） |
| 报告一致 | kill 前后 report 数字完全一致（报告是冻结快照） |
| 单飞不重复计费 | kill 后重试同一 key → 上游调用计数不增加（回放命中）或明确重跑（记录事实） |

## 验收

| 命令 | 期望 |
| --- | --- |
| `bash scripts/kill_instance_drill.sh` | 全流程 PASS；输出含两次 `X-Instance-Id`（不同值）与一致性断言 |
| 证据 | M6 ACCEPTANCE §kill 实例 贴输出（含 kill→恢复耗时） |

## 不做

- 不做混沌工程平台化（只这一条 drill）；不做网络分区模拟；不做多可用区。

