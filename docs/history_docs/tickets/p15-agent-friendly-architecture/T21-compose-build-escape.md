# T21 构建闸门出口适配 compose v5（P15-8 / P45 收尾）

Type: prototype
Status: resolved
Blocked by: 无
唯一写入路径: `scripts/`（红线内：三个构建栈脚本的构建调用行）与 `compose.yaml`（仅当原型结论要求改 build.network 时，且需在证据里留证）

## 五栏

- 范围：读 `docs/HANDOFF.md` §4（P45 与 Docker 构建代理口径）、`scripts/compose_smoke.sh` 与两个 drill 脚本的构建调用、PROBLEMS.md P15-8、T15-EVIDENCE 的环境事实。
- 唯一写入路径：见上。
- 验收口径（原始输出贴进 T21-EVIDENCE.md）：
  1. 原型先行：两个候选（构建参数授权 vs build.network 改 default）各真跑一次构建，记录网络可达性（代理/镜像站）与耗时，用读数定方向；
  2. 落地方向：`bash scripts/compose_smoke.sh` 与至少一个 drill 的构建步在本机 exit 0（不再需要 /tmp 覆写）；
  3. `bash scripts/verify.sh --layer scripts` 仍退出 0；
  4. 运行形态零变化（被断言的五条部署默认值读数不变）。
- 红线：不改部署运行形态（网络/端口/副本数）；不动 `deploy/nginx.conf`；不引依赖；不 commit/push/开 PR。
- 不接受的自由度：不许只在本机绕过写进脚本（修复必须在干净环境可复现）；不许静默放宽闸门（授权参数必须显式、注释 why）；原型结论不许跳过直接拍脑袋。

## 红绿纪律

原型（读数定方向）→ 最小落地 → 复跑绿。

## 意图复述与实现决定交代

开工先把 `## 意图复述`（三行）追加进 T21-EVIDENCE.md；收工追加 `## 实现决定交代`（三栏表），没有写「无」，不许留空。
## Answer

构建出口落成 `compose build --print | buildx bake --allow=network.host -f -`（显式授权、compose.yaml 零改动）；原型 A/B 双跑用读数定向（含 A1 反例）；三个构建栈脚本全修。

### 追记（出票方验收）

- 冒烟复跑 ALL CHECKS PASSED exit 0（无需任何覆写）；kill_instance_drill 99.91s 绿、接管 373ms。
- 变异演示：摘掉 `--allow=network.host` → 回到「Pass \"--allow=network.host\" to grant requested privileges」exit 1，恢复逐字节一致。
- 写入面 3 个脚本，compose.yaml / deploy/ 零改动（git diff 空）。
- 未验证项采纳：CI runner 的 compose 2.38.2 行为、fault_injection 全量真跑——留验收包「未验证清单」。
