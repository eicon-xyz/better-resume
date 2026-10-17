# P13-T3 — 接进 verify 分层并同步层图

- Status: done（红绿已过，待用户验收）
- Blocked by: T2
- 唯一写入路径：`scripts/verify.sh` 与 `apps/api/tests/test_verify_script.py`

> 阶段：P13（假模型驱动的黄金路径 E2E）。依据 `README.md` §1.2 现状表与 §1.3。
> Q1 已定：**新层 `e2e`**，不并入 `deploy`。
> 纪律：先写会红的用例，再写最小实现（垂直切片）；只 mock 系统边界；断言走公开行为。
## 目标

把 T2 的断言模式接进 `scripts/verify.sh`，让 nightly 与本地收口都能跑到它；层图与守卫测试同步。

## 红-绿切片

| # | 用例 | 断言 |
| --- | --- | --- |
| 1 | 层图守卫（**先红**） | `tests/test_verify_script.py` 钉住新层与其命令；未接线前该用例红 |
| 2 | `--list` 渲染出新层 | `bash scripts/verify.sh --list` 输出含新层与其命令（层图由层计划渲染，P44 的既有机制） |
| 3 | `--layer all` 的组成不变 | `all = unit + coverage + contract + scripts`；起栈类层仍只在 nightly / 手动（不要把需要 docker 的层塞进 `all`，否则本地收口会因沙箱跑不动而红） |

## 红线

- 只写这两个文件；不动其它层既有命令。
- 层图**逐字**钉住（P9 的既有做法：`pin the map verbatim`）。
- `--list` 必须由层计划渲染，不要手写第二份（P44 的教训）。
- shell 脚本 `set -euo pipefail`；改完 `bash -n` 过一遍。

## 验收

| 命令 | 期望 |
| --- | --- |
| `bash scripts/verify.sh --list` | 含新层；其余层与命令未变 |
| `cd apps/api && uv run pytest -q tests/test_verify_script.py --junitxml=/tmp/v.xml` | 全绿 |
| `bash scripts/verify.sh --layer scripts` | ALL PASS |
| `bash -n scripts/verify.sh` | 通过 |

## 不做

- 不把新层塞进 CI 的双 job（它们跑 unit/contract/coverage/scripts）；起栈类层留在 nightly 与手动。
- 不改 `.github/workflows/*.yml`（若 Q1 的结论要求改，另开票据）。

## 意图复述

把 T2 已实现的断言模式接进 `scripts/verify.sh`：新增独立层 `e2e`（Q1 已定，不并入 `deploy`），其唯一入口是共享契约 `cd apps/api && uv run python scripts/interview_smoke.py --model smoke-fake --assert`；该脚本默认 `--assert` 覆盖黄金路径、两类降级与无 category 回退形态（Q2 要求两个形态都被某一层真跑，e2e 就是那一层）。层图由层计划渲染，`--list` 只是渲染结果；`e2e` 不进 `--layer all`（组成仍为 unit + coverage + contract + scripts），也不进 CI 双 job。层图守卫按 P9/P44 既有做法先红后绿，把每层 `--list` 文案与 `--dry-run` 展开逐字钉住。

## 实现决定交代

| 决定 | 取舍 | 可实测理由 |
| --- | --- | --- |
| `e2e` 插在 `LAYER_ORDER` 的 `deploy` 之后 | 其它既有层相对顺序一字不动，只在此处新增一个词 | `git diff scripts/verify.sh` 的 LAYER_ORDER 只有一行变化；`--list` 的 diff 只在 deploy 块后多出 e2e 两行 |
| e2e 用层标签 `all:`（与 deploy/fault/soak 一致） | e2e 与 scope 无关，不随 `--scope api|web` 裁剪 | `bash scripts/verify.sh --layer e2e --scope web --dry-run` 与 `--scope all` 打印同一命令 |
| `--list` 不为 e2e 增加注释行 | 注释会引入命令原文之外的新口径 | `--list` diff 里 e2e 块只有标签行 + 命令行 |
| 入口命令原样用共享契约 | 不自造命令，T4 扩展脚本时层不漂 | `grep -n interview_smoke scripts/verify.sh` 输出与交接包契约逐字一致 |
| e2e 不进 `ALL_PARTS`/`build_all` | 起栈层不能进本地收口 | `--layer all --dry-run` 仍为 unit+coverage+contract+scripts，无 interview_smoke |
| 守卫沿用既有参数化逐字断言 | 不加 substring、不改宽泛断言 | 未接线时 `[e2e]` 用例报 `unknown layer: e2e` 红；接线后 `test_verify_script.py` 27 例全绿 |
| 不动 real 预算守卫与 shell 纪律 | 红线 | `bash -n scripts/verify.sh` 退出 0；`git diff -- .github/workflows` 为空；`set -euo pipefail` 未改 |
| e2e 实跑留给用户 | 沙箱无 docker，buildx 必失败（Q3） | AI 只自证 `--list`/`--dry-run` 与守卫；`--layer e2e` 的端到端读数未验证 |
