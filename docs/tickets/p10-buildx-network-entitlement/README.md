# P10 提案：nightly 构建被 buildx 0.37.2 的 network.host 同意闸门打死（P45）

> 现象：**nightly 连续两晚全红**（2026-10-09 / 2026-10-10，run 37911073318 / 38039021069），
> 都死在 deploy 层第一步 `compose_smoke.sh`，14 秒即 exit 1。
> 状态：**待你点头**（闸门 1）。诊断已完成（§1，全部针对 primary source 与 CI 原始日志），
> 修法与验收口径见 §3/§5；需要你在 §7 拍两件事。

## 1. 根因（已定，非推断）

失败原文（两次逐字相同，取 10-10 那次）：

```
[1/2] bash scripts/compose_smoke.sh
== compose config is valid
PASS: docker compose config
== postgres + redis, then seed the smoke-fake model row
#1 [internal] load local bake definitions
additional privileges requested: pass "--allow=network.host" to grant requested privileges
FAIL: bash scripts/compose_smoke.sh (log: var/evidence/20261010T084610Z-deploy/01.log)
```

### 1.1 触发者是 GitHub runner 镜像，不是本仓库的改动

| 证据 | 值 |
| --- | --- |
| 最后一次绿（10-08） | runner 镜像 `ubuntu24/20260927.320`，Buildx **0.37.1** |
| 首次红（10-09 09:24） | runner 镜像 `ubuntu24/20261004.327`，Buildx **0.37.2** |
| 同镜像内其它版本 | Docker 28.0.4（未变）、Compose 2.38.2（未变） |
| 窗口内本仓库的构建面改动 | `git diff --stat d1b764c..cb439e7 -- compose.yaml apps/*/Dockerfile scripts/*drill*.sh .github/workflows/ deploy/` → **空** |

两次红都发生在 **`cb439e7`（10-09 02:56 合并的 PR #24）** 这个 SHA 上，而 10-09 09:24 那次运行时我的分支**已合并 6 小时**、
10-08 的绿跑在 `d1b764c`；把「本仓库引入」这条排除掉的决定性证据是：**窗口内构建面零改动**。

### 1.2 机制（buildx 上游安全修复 + 我们的配置）

三条 primary source 拼出完整因果链：

1. **buildx v0.37.2 release notes**：
   > Bake with `--progress=rawjson` now rejects ungranted entitlements instead of skipping the consent check.
   对应 **GHSA-gwr2-q96m-6682**（severity high）："Buildx bake requires the user to grant entitlements with `--allow` or an interactive prompt… Under `--progress=rawjson` that consent step is skipped. Fixed in v0.37.2."
2. **Compose 走的就是 bake + rawjson**：`compose/pkg/compose/build_bake.go` → `args := []string{"bake", "--file", "-", "--progress", "rawjson", ...}`，
   且它只补 `--allow fs.read=…` 与 `--allow security.insecure`，**从不补 `network.host`**（2.38.2 与 main 都如此，已逐行核对）。
3. **我们的 compose 确实在请求 host 网络**：`compose.yaml` 的 `x-api-build` 与 nginx 的 build 块各有 `network: host`（2026-09-14 引入，注释写明是为 WSL2 本机代理）。
   buildx 的 `normalize()` 见到 `NetworkMode=host` 会自动往 entitlements 里塞 `network.host` → 构建**要求**该权限，而 Compose 从不**授予**它 → 0.37.2 起硬失败。

**一句话**：我们的构建一直要求 `network.host`，以前是 buildx 的检查被跳过（CVE 形状），0.37.2 补上检查后就红了。

### 1.3 为什么不是「加一行 entitlements 就好」

社区 issue 的期望是「在 compose 里声明 `build.entitlements: [network.host]`」。**对这条路径无效**，已核对源码：

- buildx 的闸门把 **CLI 的 `--allow`**（`ent := bake.ParseEntitlements(in.allow)`，commands/bake.go:137）与 **构建选项里的 Allow** 分开比对；
- bake 文件里的 `entitlements:` 只进 `bo.Allow`（bake.go:1871），随后 `Validate` 把「要求了但没授予」的项记进 `expected` → `exp.Check()` 报同一条错；
- 结论：**只要构建请求 host 网络，而 Compose 的 bake 路径不给 `--allow network.host`，声明 entitlements 也过不去**。

这也解释了为什么它是环境相关：本机 buildx 0.35.0 尚无此检查，所以我**无法在本机复现**（本机 docker 构建另受沙箱限制，见 §6）。

## 2. 范围 / 不做

**做**：让默认（CI 与普通 `docker compose` 用户）构建**不再请求** host 网络，把「本机代理」这件事变成显式的、只在本机开的开关；补一条守卫防复发；把环境事实落回 HANDOFF §4。

**不做**：
1. 不改容器**运行时**网络（只动 build 阶段的 network）。
2. 不改 Dockerfile / 镜像内容。
3. 不动真机层（本轮零供应商调用）。
4. 不动 10-08 之前就存在的任何演练逻辑。
5. 不追 `docs/architecture/`（他人未跟踪产物）。

## 3. 方案（推荐 A；B/C 见 §7）

### 方案 A：默认不请求 host 网络，本机按需显式打开（推荐）

```diff
compose.yaml  (x-api-build 与 nginx 两处)
-  network: host
+  # 仅本机（WSL2 + Docker Desktop 代理）需要：export BR_BUILD_NETWORK=host
+  network: ${BR_BUILD_NETWORK:-default}
```

- CI / 普通用户不设该变量 → `network: default` → 不再请求 `network.host` → 闸门不触发；
- 本机需要代理时设 `BR_BUILD_NETWORK=host`；此时在 buildx ≥0.37.2 上还要 `COMPOSE_BAKE=false`（bake 路径拿不到授予，而 legacy 路径会把 entitlements 直接交给 buildkit，已核对 `build.go:499 Allow:`）——两条一起写进 HANDOFF。
- 为什么 CI 不需要 host 网络：CI 无代理（`BR_LIBRARY_PREFIX` 等本机变量都没设），构建只需常规出网（拉 base image / `uv sync`），bridge 即可。**这条是推断，验收要用 §5 的分支 dispatch 实测**。

### 3.1 守卫（红-绿）

在既有的 `apps/api/tests/test_deploy_manifest.py` 加一条：**build 块不得硬编码 host 网络**（默认必须是「不请求」）。
现状（`network: host` 字面量）→ **红**；改成 `${BR_BUILD_NETWORK:-default}` → **绿**。
这样下次有人图省事写回 `network: host`，本地就会先红，而不是等 nightly。

## 4. 交付物

| 文件 | 内容 |
| --- | --- |
| `compose.yaml` | 两处 build 的 network 改为可覆盖，默认 default；注释说明本机怎么开 |
| `apps/api/tests/test_deploy_manifest.py` | 新守卫：build 块不得硬编码 host 网络 |
| `.env.example` | 补 `BR_BUILD_NETWORK` 变量名（只写名字，不写值） |
| `docs/HANDOFF.md` §4 | 环境事实更新：本机代理构建要 `BR_BUILD_NETWORK=host` + `COMPOSE_BAKE=false`，并记 P45 的因果 |
| `docs/tickets/p10-buildx-network-entitlement/` | 本 README ＋ `PROBLEMS.md`（P45）＋ `ACCEPTANCE.md`（红绿原始输出、未验证项、偏差） |

## 5. 测试与验收口径

1. **红-绿**：先写守卫（对现状红）→ 改 `compose.yaml` → 绿；原始输出进 ACCEPTANCE。
2. `docker compose config` 在「不设变量」与「设 `BR_BUILD_NETWORK=host`」两种情况下都通过，且渲染出的 `network` 分别是 `default` / `host`（本机可验）。
3. **真正的那一步**：把分支推上去，用 `gh workflow run nightly.yml --ref <branch>` **在分支上实跑一次 nightly**（docker-only，零供应商花费），确认 deploy 层过、fault 层过。
   —— 本机 docker 构建受沙箱限制跑不了（§6），所以这一步是唯一能证伪「CI 不需要 host 网络」的手段。
4. 后端全量（带 `BR_*`，junitxml 读数）＋ `--layer contract`（ruff/alembic/契约三件套）全绿。
5. `python3 scripts/verify_audit_evidence.py --strict` 仍 `unverifiable: 0`（本轮不改被引证文件）。

## 6. 诚实清单（本提案自身的未验证项）

1. **本机无法复现**：本机 buildx 是 0.35.0（无此检查），且沙箱下 `docker build` 必失败（`failed to update builder last activity time: … permission denied`）。复现依赖 CI 侧证据，条款见 §1.1。
2. **「CI 不需要 host 网络」是推断**，不是实测；由 §5.3 的分支 dispatch 证伪或证实。
3. 本机 `docker compose config` 是 **v5.3.1**，runner 是 **2.38.2**；变量插值语义跨版本稳定，但严格说「同一版本上的行为」未验。
4. 若你本机（WSL2）代理构建在改后变红，那是**预期内的**——需要按 §3 设两个变量；这条只能由你在本机确认。

## 7. 需要你拍板

**Q1：修法**
- **A（推荐）**：`network: ${BR_BUILD_NETWORK:-default}`——默认不请求 host 网络（CI 与普通用户直接好），本机显式开；代价是本机要设两个变量。
- **B**：保留 `network: host`，在三个演练脚本与 CI 里设 `COMPOSE_BAKE=false`——改动最小、回到 10-08 的行为；代价是**整个栈放弃 bake**，且人手敲 `docker compose build` 仍会撞墙。
- **C**：彻底去掉 host 网络，本机改用 `host.docker.internal` + `extra_hosts` 走代理——根治，但要动你的 WSL2 代理用法，且我无法在本机验证。

**Q2：验收方式**
- **A（推荐）**：改完推分支 → `gh workflow run nightly.yml --ref <branch>` 实跑一次 → 绿了再开 PR（PR 正文带这次 run 的编号）。
- **B**：只本地红-绿 + `compose config` 验证，直接开 PR，让合并后的 schedule 去验。

