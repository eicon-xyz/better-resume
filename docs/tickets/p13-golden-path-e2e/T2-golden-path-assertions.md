# P13-T2 — 黄金路径可断言：假模型 + 走 nginx + 退出码

- Status: ready-for-agent
- Blocked by: T1
- 唯一写入路径：`apps/api/scripts/interview_smoke.py`

> 阶段：P13（假模型驱动的黄金路径 E2E）。依据 `README.md` §1.2 现状表与 §1.3。
> Q3 已定：AI 交脚本与单元级断言，**端到端读数由用户在宿主机跑并回填**；验收包里两类读数分开列。
> 纪律：先写会红的用例，再写最小实现（垂直切片）；只 mock 系统边界；断言走公开行为。
## 目标

`apps/api/scripts/interview_smoke.py` 已经走完整链路（上传→答题→结束→打印报告），但要真 key、只打印、不在任何 verify 层。
本票让它**一份实现、两种调用**：真模型（`real` 层，打印 + 带 `usage`）与假模型（新层，**断言 + 退出码**）。

**不做成两份实现**——`docs/audit/units/media.json` 已经记过「两份可以无限漂移」这个坏味道。

## 红-绿切片

| # | 用例 | 断言 |
| --- | --- | --- |
| 1 | 断言模式真的会红（**先写**） | 故意把期望改坏（如期望 4 题）→ **非 0 退出**；不是只打印 FAIL 后 exit 0 |
| 2 | 假模型跑通全路径 | 上传 → 出 5 题 → 答题 → 追问 → 结束 → 报告，全部走 nginx（`http://127.0.0.1:8080`），退出码 0 |
| 3 | 每一步失败都能指名 | 失败输出含：哪一步 + 原始响应 + 相关 DB 行（若可查） |
| 4 | 真模型路径不退化 | 不带断言开关时行为与现在一致（打印报告 + `usage`） |

## 红线

- 只写 `apps/api/scripts/interview_smoke.py`（如需测试则加 `apps/api/tests/test_interview_smoke_script.py`，与既有 `test_*_script.py` 同族）。
- 客户端一律显式兜底（`trust_env=False` / `proxy=None`）、显式 `open_timeout` / `close_timeout`（`AGENTS.md` §开发规范）。
- 证据诚实：假供应商无 `usage`，**不许拿假的冒充真的**；断言模式必须标明用的是 `smoke-fake`。
- 不留「默认关闭没人跑」的开关——两种调用都必须真的被某一层跑到。
- 不 commit / push / 开 PR。

## 验收

| 命令 | 期望 |
| --- | --- |
| 断言模式的坏期望演示 | 非 0 退出 + 原始输出贴进验收包 |
| `cd apps/api && uv run python scripts/interview_smoke.py --model smoke-fake --assert`（栈在跑时） | 退出码 0，逐条 PASS |
| `bash scripts/verify.sh --layer scripts` | ALL PASS（新脚本被 `check_scripts.py` 扫到且无 SyntaxWarning） |
| `uv run pytest -q tests/ --junitxml=/tmp/x.xml` | 全绿、0 skipped |

## 不做

- 不动 `real` 层的预算守卫；不碰真机四条链路；不改 `compose.yaml` 拓扑。
