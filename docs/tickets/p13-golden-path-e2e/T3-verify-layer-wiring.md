# P13-T3 — 接进 verify 分层并同步层图

- Status: ready-for-agent
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
