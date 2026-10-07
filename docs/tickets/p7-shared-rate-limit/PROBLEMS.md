# P7 问题台账（P42–P43）

## P42 / 探针与演练共用同一个限流桶：钉小 rate 把演练自己打成 429

- **现象**：`kill_instance_drill.sh` exit=1，driver 在 `POST /api/v1/interview/sessions/{id}/answers`
  抛 `httpx.HTTPStatusError: Client error '429 Too Many Requests'`。
- **我当时的做法**：为了让"共享配额探针"有确定边界，给栈 `export BR_RATE_LIMIT__ANSWER_PER_SECOND=0.01`
  （capacity = max(1, round(0.01 × burst 2)) = 1）。
- **真根因**：探针与演练**共用同一个桶**（answer），而 rate 是按桶配置、不区分身份——
  钉小 rate 等于把演练自己的答题也钉成"第二次必 429"。
- **修法**：**不钉 rate**。探针改用全新身份（新会话 → 新桶）连打 7 次（> 2 × capacity），断言
  "放行数 ≤ capacity + 1（容忍突发回填）+ 每个响应 scope=shared + Redis 里有 `br:rl:` 键"；
  每副本一份配额时会到 2 × capacity，且 scope=instance、Redis 无键。
- **教训**（与 m6 的 P41 同族）：**先怀疑注入/取样方式，再怀疑参数**——这里是"先怀疑探针怎么取样，
  再怀疑配额本身"。

## P43 / Redis 分区期间认证路径先死：限流降级只能在认证之前观测

- **现象**：带断言的 `redis-partition` 第一次跑出 `note: ratelimit_during_partition=None/None` 并判 FAIL。
- **我当时的假设**：分区期间"受限端点应返回业务状态 + `scope=instance`"。
- **真根因**：带 cookie 的请求要先过会话存储（Redis）→ 分区时 `auth_during_partition=ReadTimeout`，
  请求在走到限流判定之前就超时了。**认证路径自己也依赖 Redis，限流降级在这条路径上根本不可观测**。
- **修法**：分区期间改用**匿名**探针（IP 身份，不碰会话存储）→ `401/instance`，即"401 之前那一步正是
  限流 middleware 的决定"。断言成三态：前 `shared` → 中 `<500 且 instance` → 后 `shared`。
- **教训**：观测点要放在**被测组件真正做决定的那一层**，别放在它下游的依赖上——这是 P27
  （探针漏前置状态会把 503 读成 401）的镜像版本。

## 未记为问题，但建议进 `AGENTS.md` 环境准备

- **Docker 构建在 `workspace-write` 沙箱下必然失败**：buildx 要写工作区外的
  `/root/.docker/buildx/activity/`，报 `failed to update builder last activity time: ... permission denied`；
  需要更宽的沙箱模式。**另外**：`docker compose build ... | tail` 会把退出码换成 `tail` 的 0——
  本轮第一次冒烟的"exit 0"就是这么来的假象（P31 的同族：退出码/标签与真实展开会各自漂移）。
