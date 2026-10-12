# P13-T2 — 黄金路径可断言：假模型 + 走 nginx + 退出码

- Status: done（红绿已过，待用户验收）
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

## 意图复述

（开工前，执行方复述）

把 apps/api/scripts/interview_smoke.py 从「只打印、要真 key」改成同一份实现支持两种调用：
默认（不带 --assert）保持现在的真模型路径——同样的请求顺序、同样的打印输出；新增 --assert
假模型路径——上游固定 smoke-fake、默认走 nginx(8080)、按契约与 D23 断言整条黄金路径
（上传 → 5 题 → 答题 → 追问 → 结束 → 报告：题量、每题合法 category、追问继承主问题 category、
报告结构与按类聚合一致），每步失败打印「步骤名 + 原始响应 + 可查的 DB 行/查询」，并以非 0 退出码收尾。
断言期望可注入（--expect-questions），故意改坏期望即可一条命令演示红。端到端读数由用户在宿主机跑并回填，
沙箱内只交单元级红-绿与脚本级可演示性。

## 实现决定交代

（收工时；下表只列 spec 与交接包未明说、由我拍定的点）

| spec 未覆盖、我自行拍定的决定 | 为什么这么拍 | 我明确没做的 |
| --- | --- | --- |
| --assert 必须配 --model smoke-fake，否则 argparse 直接报错退出 2 | 红线要求「断言模式必须标明用的是 smoke-fake、不许拿假的冒充真的」；把供应商名做成硬门槛比事后打印一行更强 | 没留跳过校验的隐藏开关；没做 allow-real 之类的旁路 |
| 请求题量 --count 与期望值 --expect-questions 分开 | 假供应商按 prompt 里的题数出题；若期望值同时驱动请求，期望 4 就会真的请求到 4，坏期望演示永远不会红。分开后期望是纯断言注入，请求仍是契约 5 | 没让 --expect-questions 改动请求；没在断言失败后反写期望 |
| 真模型分支保留原样：默认 base 8040、请求 count=3、答题循环上限 6；断言分支用 base 8080、count=5、循环上限 count*(1+2) | 默认行为不许变；断言是新增调用，两套默认值在 parse_args 里按 assert_mode 解析 | 没把真模型路径改成 5 题或循环到结束；没重排任何成功路径的打印 |
| 统一每步的 HTTP 语义：所有请求先走一个命名步骤的 2xx 检查，连接层异常也记成「步骤名 + transport error」 | 票据第 3 条要求每步失败能指名；原脚本只在 questions/finish 上 raise_for_status，连接失败会给裸 traceback | 没为跑通放宽检查；没吞异常；成功路径的打印与请求顺序逐字保留 |
| --expect-questions 只允许 1..10 | 与契约 count 的 clamp 区间一致 | 没让越界值静默通过 |
| DB 行探针做成可注入（run 的 db_probe 参数），仅 __main__ 的断言路径启用；探针不可用时打印可复制的 psql 命令 | 「相关 DB 行（若可查）」要真去查，但单元测试不能依赖 docker；分离后两端都诚实 | 没在单元测试里连 docker；没把查询结果伪装成一定有 |
| 报告不要求 summary 非空，只断言结构、维度、按类聚合与逐题类别一致 | jobs_enabled 时 summary 由 worker 异步补；T2 的黄金路径到报告结构为止 | 没轮询等待 worker summary；没断言 summary 文案 |
| 真模型路径保持只打印报告：票据括号写「打印报告 + usage」，但现状脚本没有任何 usage 打印（interview 的 REST 响应也不带 usage） | 票面正文的约束是「与现在一致」，且禁止重构既有打印；usage 属于 real_model_smoke 的 chat 流 | 没给 interview_smoke 真模型路径新增 usage 打印（会改默认输出） |


