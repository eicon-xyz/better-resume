# P4 验收包：让 nightly / weekly 真正绿（P35–P38）

> 分支 `fix/p35-cold-volume-migrate`（基于 `main` = `a30aac8`）。
> 提案：`README.md`；台账：`PROBLEMS.md`（P35–P38）。
> 一句话结论：**本机冷卷三条演练全绿、`verify.sh --layer all` 12 条命令全绿**；CI 见 §4。

## 1. 复跑命令

```bash
export PATH="$HOME/.local/bin:$PATH"
export UV_CACHE_DIR='/root/better resume/.cache/uv'

# ① 冷卷红（复现 P35；会删掉本地 pgdata/uploads——历次演练残留，migrate 可重建）
docker compose --profile smoke down -v
bash scripts/compose_smoke.sh          # 期望：relation "ai_models" does not exist

# ② 冷卷绿（三条演练，每条前都要先清卷）
docker compose --profile smoke down -v && bash scripts/compose_smoke.sh
docker compose --profile smoke down -v && bash scripts/kill_instance_drill.sh
docker compose --profile smoke down -v && bash scripts/fault_injection_drill.sh --quick

# ③ 本地收口（12 条命令；contract 层要求干净工作树，先提交再跑）
export BR_DATABASE_URL='postgresql+asyncpg://better_resume:better_resume@127.0.0.1:5433/better_resume'
export BR_REDIS_URL='redis://127.0.0.1:6379/0'
bash scripts/verify.sh --layer all

# ④ 本次新增的契约测试（hermetic，不需要 docker）
cd apps/api && uv run pytest tests/test_drill_prereqs.py tests/test_fault_probe.py -q
```

> 本机复跑需要**工作区之外**的写权限：`docker compose ... --build` 会让 buildx 写 `/root/.docker/buildx/`，
> 在 `workspace-write` 沙箱下被拒（`failed to update builder last activity time: ... permission denied`）。
> CI 上没有这个限制。

## 2. 原始输出（摘录；全文在 `var/evidence/p35/`）

### 2.1 冷卷红 —— P35 复现（`01-cold-red.log`）

```
=== pgdata volume present after down -v? ===
0
ERROR:  relation "ai_models" does not exist
LINE 1: INSERT INTO ai_models (name, provider, base_url, model_id, a...
compose_smoke exit=3
```

与 CI 的失败逐字一致（nightly run `35701690467`）。

### 2.2 冷卷绿 —— `compose_smoke.sh`（`02-cold-green.log`）

```
14 × PASS：config / smoke-fake 行 / up --wait / SPA / no-store / immutable asset /
         api+worker 非 root / REST / SSE / WS / scale api=2 / 双实例轮询 / worker 心跳
ALL CHECKS PASSED (edge: http://127.0.0.1:8080; stop with: docker compose --profile smoke down -v)
```

### 2.3 冷卷绿 —— `kill_instance_drill.sh`（`03-cold-kill-drill.log`）

```
nginx now routes to 64d8cfca5c8e (first healthy response after 4 ms in 1 attempts of 1s, kill -> recovery 260 ms)
replayed request on 64d8cfca5c8e: replayed=True score=55.0
  answer rate limited (429); retrying in 1.00s     ← P36：按 Retry-After 重试，不再 KeyError
  answer rate limited (429); retrying in 1.00s
PASS: 会话在实例被 kill 后由另一实例接管，状态、分数与冻结报告全部一致
```

### 2.4 冷卷绿 —— `fault_injection_drill.sh --quick`（`04-cold-fault-drill.log`）

```
PASS: docker compose up --wait --scale api=2
PASS: redis-pause window classified and recovery measured
PASS: redis-restart: honesty about session loss
PASS: redis network partition: no wrong answers, self-heal measured
PASS: manual failover: recovery measured, worker survived, sessions intact
== login attempt 1 -> 503; retrying in 1.0s        ← P37：登录重试
== stack not usable yet (503); retrying in 2s      ← P38：等栈真正可用再开跑
PASS: the crashed consumer's job was reclaimed and completed
PASS: crashed consumer's job reclaimed and finished
PASS: soak error rate stayed under 1%
ALL FAULT EXPERIMENTS PASSED (json: /tmp/v6-soak.json)
```

### 2.5 本地收口（`05-layer-all.log`）

```
ALL PASS (12 commands) -- evidence: var/evidence/20260923T080421Z-all
```

## 3. 数字

| 项 | 值 | 对照 |
| --- | --- | --- |
| 后端 pytest | **794 passed** | `main` 上 747（本分支改动见 §6） |
| 前端 vitest | **175 passed** | 不变 |
| scripts 层 | **44 passed** | 原 27（+17：`test_drill_prereqs.py` 首次进这一层） |
| 契约层 | 9 条命令全过（ruff / format / alembic / export_openapi --check / extract_api_index --check / eslint / tsc / check:api） | — |
| `verify.sh --layer all` | **12 条命令全绿** | — |
| 真机调用 | **0 次** | 全程 fake 上游 |

## 4. CI

（待回填：nightly `workflow_dispatch` run id + 结论）

## 5. 未验证项（诚实清单）

- **nightly / weekly 的排程尚未验证**：`schedule` 只认默认分支，本分支只能 `workflow_dispatch` 手动触发；真正那次要等合并进 `main` 后的 02:30 UTC（提案 Q3 已确认接受）。
- **weekly-full 的 60 分钟浸泡没跑**：本机只跑 `--quick`（2 分钟浸泡）。
- **冷卷绿是本机 docker 的结果**：CI runner 同样是冷卷，但这三条演练在 CI 上尚未跑过（合并前）。
- **P38 的 120s 窗口是实测拍出来的，不是推导的**：failover 之后 503 持续多久没做系统测量，只观察到「>24s 仍有 503」。若 CI 上超过 120s，worker-crash 仍会失败——届时是真实发现，不是静默通过。
- 本机复跑需要 `danger-full-access`（buildx 写工作区外）；CI 无此限制。

## 6. 与提案的偏差

提案只写「seed 前先 migrate + 补脚本回归契约 + docker 预检」。实际同一条链上还有三个缺陷，不修就达不到提案目标 1（三条演练冷卷全绿），因此一并修了：

| 偏差 | 说明 |
| --- | --- |
| 多修 P36 | `kill_instance_drill.py` 连发作答撞 2 rps 限流后以 `KeyError` 崩溃——**探针问题，产品行为是对的**（P1-B 标定） |
| 多修 P37 | `fault_probe.worker_crash` 在 failover 后立刻登录，被一个 503 打死；soak 早就修过同样的坑，只是逻辑内联在 soak 里，抽出来共享 |
| 多修 P38 | worker-crash 的**整个启动**都需要栈可用，不只是登录 → 加 `--ready-timeout`（默认 120s）就绪闸门，等不到就响亮失败 |
| Q2 落在别处 | 提案写「给 `verify.sh --layer deploy\|fault` 加 docker 预检」，实际缺口在 **`compose_smoke.sh` 自己**（另两个脚本早有守卫，只有它没有）。守卫补在真正缺的脚本里，三个脚本行为一致，`verify.sh` 不重复检查——仍要 layer 级预检的话说一声 |
| 顺手一处 | `verify.sh` 的 `add_scripts()` 原来不含 `test_drill_prereqs.py` → 补进这一层（27 → 44 例） |
