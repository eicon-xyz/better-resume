# P4 提案：让 nightly / weekly 真正绿（冷库正确性 + 脚本回归契约）

> 依据：nightly 连续 5 晚全红（2026-09-18 ~ 09-22）、weekly-full 红（09-20）；根因 = **P35**。
> 状态：**提案，等用户确认后动工**。分支 `fix/p35-cold-volume-migrate`（基于 `main` = `a30aac8`）。

## 1. 现状盘点（实测，不是印象）

| 事实 | 证据 |
| --- | --- |
| nightly 连续 5 晚失败，每次 24–31 秒 | runs `35319873282` `35429374534` `35497979631` `35576171196` `35701690467` |
| weekly-full 失败 1 次（09-20） | run `35498682542` |
| 失败点完全相同 | 日志原文 `ERROR: relation "ai_models" does not exist` → `FAIL: bash scripts/compose_smoke.sh` / `FAIL: bash scripts/fault_injection_drill.sh` |
| 本机为什么一直绿 | `better-resume_pgdata` 是**热卷**：实测 `ai_models` 有 6 行、alembic 停在 `9f2c1a7b5d31` |
| 三个脚本同构缺陷 | `compose_smoke.sh:55` / `kill_instance_drill.sh:52` / `fault_injection_drill.sh:62`：`docker compose up -d --wait postgres redis` → 立刻 `INSERT INTO ai_models` → 直到后面的 `up` 才跑 `migrate` 服务 |
| compose 其实早知道 | `compose.yaml:72` 注释：「Without it a fresh volume starts against an empty database (found the hard way in the T5 smoke)」——但演练脚本没照做 |

**性质**：与 P31–P33 同一类「本地绿、CI 红」。P2 建的自动回归网（deploy / fault / soak 层）**从第一次运行起就没绿过**。

## 2. 目标（可验收的成功标准）

1. 冷 volume 上 `compose_smoke.sh` / `kill_instance_drill.sh` / `fault_injection_drill.sh` 全部通过，不再依赖本地热卷。
2. nightly 与 weekly-full 各**真跑绿一次**（不是 dry-run、不是本地模拟）。
3. 新增回归契约把「seed 之前必须先迁移」钉住，并在旧代码上**演示红**。
4. 修后本机热卷与冷卷行为一致。

## 3. 不做

- 不改 `compose.yaml` 的服务拓扑（`migrate` 服务本身是对的，错的是脚本调用顺序）。
- 不动 CI 的 cron / 并发 / 权限 / 超时。
- 不扩大范围到 `apps/api/scripts/real_model_smoke.py:37`（它连的是宿主测试库 5433，迁移由另一条路径负责）。
- 不引入新依赖、新测试框架。

## 4. 交付物

- 三个脚本：seed 前显式执行 `docker compose run --rm migrate`（幂等；随后 `up` 再跑一次也无害）。
- 脚本回归契约（pytest，hermetic，不需要 docker）：断言三个脚本的命令顺序里 `migrate` 出现在 `INSERT INTO ai_models` **之前**。
- `docs/tickets/p4-nightly-green/PROBLEMS.md`：P35 台账（现象 / 根因 / 证据 / 修法 / 回归守卫）。
- `docs/tickets/p4-nightly-green/ACCEPTANCE.md`：冷卷复跑命令 + 原始输出 + CI run 链接 + **未验证项（诚实清单）**。

## 5. 测试与验收口径

- **红**：`docker compose --profile smoke down -v` 清卷 → 跑 `bash scripts/compose_smoke.sh` → 复现 `relation "ai_models" does not exist`，原始输出留档。
- **绿**：同一条命令在修后通过；`bash scripts/verify.sh --layer all`（12 条命令）仍全绿，四项数字（后端 / 前端 / contract / 脚本）不回退。
- **CI**：推分支后用 `workflow_dispatch` 手动触发 nightly 一次；正式那次要等合并进默认分支后的 02:30 UTC。
- **诚实清单**：逐条写清哪些是本机跑的、哪些是 CI 真跑的；没跑的写「未验证」。

## 6. 预估

- 代码：3 个脚本各 1–3 行 + 1 个测试文件；半天内。
- 时间：冷卷 `compose_smoke` 单次 3–5 分钟（要重建镜像）。
- **真机调用：0 次**（全程 fake 上游）。

## 7. 需要用户决定的问题

- **Q1**（已口头同意，动工前再确认一次）：清卷复现会删掉本地 `better-resume_pgdata` / `uploads`——里面是历次演练残留，migrate 可重建。
- **Q2**：是否顺手给 `verify.sh --layer deploy|fault` 加一条 docker 预检（无 docker 时**明确失败**，而不是假装跑过）？倾向：要——这是 P2-T6 已定的规矩。
- **Q3**：验收是否接受「合并进 main 后观察 02:30 UTC 那次 nightly 真绿」作为最后一环（schedule 只认默认分支）？
