# P10 验收包：nightly 构建的 buildx network.host 闸门（P45）

> 状态：**待用户验收**（AI 不自行宣布完成、未合并、未删分支）
> 分支：`fix/nightly-buildx-entitlement`，从 `main` = `cb439e7` 切出
> 提案：`docs/tickets/p10-buildx-network-entitlement/README.md`（用户已拍板：**认可归因 / B 修法 / A 分支实跑验收**）
> 台账：`docs/tickets/p1-post-v/PROBLEMS.md` 的 **P45**

## 0. 一句话

nightly 连续两晚红**不是本仓库引入的**：GitHub runner 镜像把 Buildx 从 0.37.1 升到 0.37.2，
而 0.37.2 修了 GHSA-gwr2-q96m-6682（bake 在 `--progress=rawjson` 下不再跳过权限同意检查），
Compose 的 bake 路径又从不授予 `network.host` —— 我们 `compose.yaml` 恰好请求了它。
按用户选的 **B**：构建栈的三个脚本各自 `export COMPOSE_BAKE=false` 回到 classic 路径，并加守卫钉住。

## 1. 根因证据链（每条都可复核）

| # | 事实 | 出处 |
| --- | --- | --- |
| 1 | 两次失败报错逐字相同，都死在 deploy 层第一步，**14 秒即 exit 1** | run 37911073318 / 38039021069 的 log-failed |
| 2 | 最后一次绿（10-08）镜像 ubuntu24/20260927.320 → Buildx **0.37.1** | run 37755604545 日志 + runner-images release 清单 |
| 3 | 首次红（10-09 09:24）镜像 ubuntu24/20261004.327 → Buildx **0.37.2**；Docker 28.0.4、Compose 2.38.2 均未变 | 同上两份清单 diff |
| 4 | 窗口内本仓库构建面零改动 | git diff --stat d1b764c..cb439e7 -- compose.yaml apps/*/Dockerfile scripts/*.sh .github/workflows/ deploy/ → 空 |
| 5 | buildx 0.37.2 的行为变化 | release notes 原文 + GHSA-gwr2-q96m-6682（"requires the user to grant entitlements with --allow"） |
| 6 | Compose 走 bake + rawjson，且只补 --allow fs.read / security.insecure | Compose 2.38.2 与 main 的 pkg/compose/build_bake.go 逐行 |
| 7 | compose.yaml 两处 build 请求 host 网络 | 本仓库 compose.yaml（2026-09-14 为 WSL2 代理引入，M6-T5 提交 137d5db） |

### 1.1 为什么「加 entitlements 声明」也修不好（写下来省一次试错）

buildx 的闸门把 **CLI 的 --allow**（ent := bake.ParseEntitlements(in.allow)，commands/bake.go:137）与**构建选项的 Allow** 分开比对：
bake 文件里的 entitlements: 只进 bo.Allow（bake/bake.go:1871），随后 Validate 把「要求了但没授予」的项记进 expected → 同一条错照旧。

## 2. 改了什么（一句话/处）

| 文件 | 改动 |
| --- | --- |
| scripts/compose_smoke.sh | 头部 export COMPOSE_BAKE=false（含 P45 因果注释） |
| scripts/kill_instance_drill.sh | 同上 |
| scripts/fault_injection_drill.sh | 同上（放在 docker 检查之前，只用 bash 内建，--help 仍可离线工作） |
| apps/api/tests/test_drill_prereqs.py | 新守卫：构建栈的脚本必须**在非注释行**里 export COMPOSE_BAKE=false |
| docs/HANDOFF.md §4 | 两条环境事实：本机人手构建要带该变量；P45 的症状/根因/修法 |
| .env.example | COMPOSE_BAKE 变量名（只写名字） |
| docs/tickets/p1-post-v/PROBLEMS.md | P45 四栏台账 |

## 3. 红 → 绿

```
$ cd apps/api && uv run pytest tests/test_drill_prereqs.py -q      # 修前
FAILED test_a_script_that_builds_the_stack_opts_out_of_bake[compose_smoke.sh]
FAILED test_a_script_that_builds_the_stack_opts_out_of_bake[kill_instance_drill.sh]
FAILED test_a_script_that_builds_the_stack_opts_out_of_bake[fault_injection_drill.sh]

$ same command after                                              # 修后
23 passed
```

### 3.1 变异证明 ×2（基线绿 → 变异红 → 恢复绿）

```
M1 把 compose_smoke.sh 的 export 改成 =true
   -> 红：...[compose_smoke.sh]                      PASS
M2 删掉 fault_injection_drill.sh 的 export
   -> 红：...[fault_injection_drill.sh]              PASS
```

### 3.2 第一版守卫是**假绿**（诚实记录，值得单独说）

第一版守卫用**子串匹配**（BAKE_OFF in body），而脚本里的解释性注释**也含有** COMPOSE_BAKE=false 这个串 ——
结果 M1/M2 两条变异都**没被抓到**：verify_mutation.sh 报 "the test stayed green on the mutation"。
改为只看非注释行里的 export COMPOSE_BAKE=false 之后，两条变异才真红。
**教训与 P31/P44 同族**：断言必须打在「真会执行的那一行」上，否则它保护的是注释。

## 4. 验收：分支上实跑 nightly（用户选的 A）

```
$ gh workflow run nightly.yml --ref fix/nightly-buildx-entitlement
https://github.com/eicon-xyz/better-resume/actions/runs/38042100551

步骤状态（实测）：
  5 Deploy layer (compose smoke + kill drill)   success   <- 就是连续两晚红掉的那一步
  6 Fault layer (quick soak)                    <- 见下方最终读数
```

这一步是本次修复唯一的**证伪手段**：本机 buildx 是 0.35.0（没有这个检查）且沙箱下 docker build 必失败，
所以「CI 不需要 host 网络」只能靠 CI 自己证。

### 4.1 run 38042100551 最终读数

```
run 38042100551 @ 7d4d462（本分支）   结论：success   09:38:30 → 09:45:43（7m13s）
  5 Deploy layer (compose smoke + kill drill)   success
  6 Fault layer (quick soak)                    success

deploy 层内部读数（原始日志摘录）：
  PASS: worker runs as uid 999 (non-root)
  PASS: scale api=2
  PASS: worker heartbeat key exists
  ALL CHECKS PASSED (edge: http://127.0.0.1:8080; stop with: docker compose --profile smoke down -v)
  ALL PASS (2 commands) -- evidence: var/evidence/20261010T093835Z-deploy
  PASS: docker compose up --wait --scale api=2          <- kill 演练

对照：同一 workflow 在 cb439e7 上的前两次运行（2026-10-09 / 10-10）都死在
      [5] Deploy layer 的第一步，14 秒 exit 1。
```

## 5. 本机收口

```
bash scripts/verify.sh --layer all
ALL PASS (16 commands) -- evidence: var/evidence/20261010T093858Z-all
  后端 896 passed / 0 failed / 0 skipped（105.26s）
```

## 6. 未验证项（诚实清单）

1. **本机无法复现原故障**：本机 buildx 0.35.0 尚无该检查（这正是它环境相关的原因）；
   且沙箱下 docker build 必失败（failed to update builder last activity time: permission denied），
   所以「改前红、改后绿」在本机只能证明到守卫这一层。
2. **本机 docker compose 是 v5.3.1，runner 是 2.38.2**：COMPOSE_BAKE 语义两版本一致（已逐行核对 2.38.2 的 buildWithBake），但同版本实测未做。
3. **只覆盖演练脚本这条路**：人手在生产机敲 docker compose up -d --build 仍会撞闸门——已写进 HANDOFF §4 与 .env.example，但**没有**在 compose.yaml 层面兜住（那是方案 A，用户选了 B）。
4. **weekly-full 未跑**：它同样构建栈（同一 bug 类），本轮只 dispatch 了 nightly。
5. **真机层零调用**（--layer real 未跑）。
6. 未重锚任何审计引证（本轮没改被 docs/audit/units/*.json 引用的文件）。

## 7. 与提案的偏差

1. **提案 §3 推荐 A，用户选 B**：因此「人手敲命令也会中」被保留为已知项（§6.3），§5 的兜底范围只到脚本与文档。
2. **守卫位置**：提案说加在 test_deploy_manifest.py，实际加在 test_drill_prereqs.py —— 更贴：那个文件本来就是「三个演练脚本的前置与契约」的家
   （P35 的 DRILL_SCRIPTS 常量就在那里），而 P45 的约束对象正是这三个脚本。

## 8. 复跑命令

```bash
# 守卫（3 个参数化）与它的变异证明
cd apps/api && uv run pytest tests/test_drill_prereqs.py -q -p no:randomly
bash scripts/verify_mutation.sh /
  --test "cd '/root/better resume/apps/api' && ./.venv/bin/python -m pytest tests/test_drill_prereqs.py -q -p no:randomly" /
  --file scripts/compose_smoke.sh --find "export COMPOSE_BAKE=false" --replace "export COMPOSE_BAKE=true"
# 分支上的 nightly（docker-only，零供应商花费）
gh workflow run nightly.yml --ref fix/nightly-buildx-entitlement
```

