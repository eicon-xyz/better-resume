# P13-T4 — 降级路径与类别一致性的断言

- Status: done（红绿已过，待用户验收）
- Blocked by: T2
- 唯一写入路径：`apps/api/scripts/interview_smoke.py`（追加场景）与所需 fixture

> 阶段：P13（假模型驱动的黄金路径 E2E）。依据 `README.md` §1.2 现状表与 §1.3。
> Q3 已定（同 T2）：AI 交脚本与单元级断言，**端到端读数由用户在宿主机跑并回填**；验收包里两类读数分开列。
> 纪律：先写会红的用例，再写最小实现（垂直切片）；只 mock 系统边界；断言走公开行为。
## 目标

把 `docs/MANUAL-TESTING.md` §1.5 第 10–13 项的**语义层**变成断言：两类降级 + 类别落库 + 按类聚合一致性。

## 红-绿切片

| # | 用例 | 断言 |
| --- | --- | --- |
| 1 | 无文本层 PDF | 不报错；仍出 5 题；`interview_sessions.resume_warnings` 落库；降级原因在响应/报告里明示 |
| 2 | 技能与语料无关的简历 | 仍出题；降级原因为「未匹配到八股语料」 |
| 3 | 类别落库与继承 | 每题 `interview_questions.category` ∈ 三枚举；追问的 `category` == 主问题的 |
| 4 | 按类聚合一致 | `category_breakdown` 的题数与逐题 `category` 一致；某类 < 2 题 → 不出分数 + 「样本不足」 |

fixture 注意：合成 PDF 的 **CJK 分隔符会被字体抹掉**（`docs/tickets/p11-resume-driven-questions/PROBLEMS.md` §2 记过这个坑）——
需要真实技能串时用 ASCII 逗号分隔的那份构造方式。

## 红线

- 查库用既有模式：`docker compose exec -T postgres psql -v ON_ERROR_STOP=1`（见 `scripts/compose_smoke.sh:110`）。
- 每次跑用**唯一 run id**，不依赖上一次的残留数据；跑完的共享状态自己还原。
- 断言的**预期来自契约与 D23**，不是「系统返回了什么」——`CODING_STANDARDS.md` §6 第 1 条。
- 只写 T2 那个脚本与 fixture；不动引擎与迁移。

## 验收

| 命令 | 期望 |
| --- | --- |
| 断言模式跑四个场景 | 逐条 PASS；证据落 `var/evidence/<ts>-e2e/` |
| 故意改坏一条断言 | 非 0 退出（贴原始输出） |
| `uv run pytest -q --junitxml=/tmp/x.xml` | 全绿、0 skipped |

## 不做

- 不断言「题目整体偏项目」——那依赖真模型是否理会配比提示，假供应商测不出（`README.md` §1.4）。
- 不做报告页的视觉断言（渲染层留给人）。

## 意图复述

把 docs/MANUAL-TESTING.md §1.5 第 10–13 项里语义层可自动化的部分，做成 interview_smoke.py 断言模式的一部分：两类降级（无文本层 PDF、技能与语料无关的简历）都必须「不报错、仍出 5 题、降级原因明示、resume_warnings 落库」；每题 category 落在三枚举内，追问的 category 继承主问题；报告 category_breakdown 与逐题 category 一致，某类计分题少于 2 道时 score 为空且评语为「样本不足」。断言逻辑先在不依赖栈的 FakeStack 单测里红-绿可证，端到端读数由用户在宿主机跑并回填。

## 实现决定交代

| 决定 | 理由 | 怎么实测 |
| --- | --- | --- |
| 四个场景共用一个入口，默认全跑；--scenario 仅调试过滤 | 共享契约要求默认全覆盖，不留「默认关闭没人跑」的分支 | 宿主机跑 --model smoke-fake --assert 打印四个 scenario 头；单测 test_default_assert_mode_runs_every_scenario 断到 4 个会话 |
| 场景由简历 fixture 决定，上传文件名带上场景名（golden / no-text-layer / unmatched-corpus / no-category） | 真实 API 不看文件名，FakeStack 据此在 HTTP 边界选应答，不 mock 引擎内部 | test_default_assert_mode_runs_every_scenario 断言四个会话的 scenario 顺序 |
| 无文本层 fixture 用 reportlab 画只有图形的空页 | 与 MANUAL-TESTING §1.5 第 10 项一致；不可解析简历返回空 ResumeContext，故该场景 resume_warnings 只能断言空列表往返，非空内容由第 11 项场景承担 | test_fixture_grounds_each_scenario 断到 ResumeParseError.code == text_layer_missing |
| 无关技能 fixture 是单行 ASCII 技能串（COBOL, Fortran, Pascal, Ada），无章节无联系方式 | 让降级明示同时有 degraded_reasons 与 resume_warnings 两处内容可断言；遵循 P11 PROBLEMS §2 的 ASCII 逗号分隔 | test_fixture_grounds_each_scenario 断到 warnings 为 no_sections_detected 与 no_contact_found 且语料为空；test_a_wrong_resume_warning_is_red 喂空 warnings 非 0 退出 |
| 无 category 回退形态 = 黄金简历加一行含 NO_CATEGORY_MARKER 的技能补充 | 不改引擎与 fake；标记经简历文本进入 build_messages 的 render_context，fake 看到后省略 category，引擎按 D23 回退 | test_no_category_marker_matches_the_fake_vendor 断脚本常量等于 fake 常量；test_fixture_grounds_each_scenario 断标记出现在 render_context；真实栈仍断 category 属三枚举 |
| 降级断言读 HTTP 响应（questions 顶层 degraded/degraded_reasons 与 session 视图；报告再核 session 两字段） | 单测不许依赖 docker，FakeStack 站在 HTTP 边界；psql 落库核对写进用户 e2e 清单 | test_a_wrong_degradation_reason_is_red 与 test_a_wrong_resume_warning_is_red 喂错数据后脚本非 0 退出 |
| 每次 --assert 运行生成唯一 run_user（m2-smoke- 加 8 位 hex）并打印 | 唯一 run id，不依赖上次残留；psql 可按打印值精确过滤 | 连跑两次，各自按 run_user 在 interview_sessions 恰好查到 4 行 |
| 按类聚合一致与「少于 2 题样本不足」沿用既有 report: category aggregates match the turns 检查 | 契约要求每类 count/score/comment 齐全且与逐题一致 | test_a_category_aggregate_mismatch_is_red 与 test_a_thin_category_with_the_wrong_comment_is_red |
| 脚本降级码用本地常量并加漂移守卫；fixture 期望由真实 HybridResumeParser 与 filter_corpus 钉住 | 预期来自契约与 D23，不按系统返回反写 | test_degradation_codes_match_the_engine 与 test_fixture_grounds_each_scenario |
| 断言客户端对 429 按 Retry-After 退避重试（上限 5 次），复用同一 request_id | answer 桶 2/s、容量 4，一次 15 答的快速行走会被限流；退避是客户端该有的行为，不改变断言语义，request_id 幂等保证重试安全 | 本地非 docker 实跑（真实引擎 + 本地 fake 供应商 + redis 限流后端）：四场景 exit 0、18 次 429 重试、0 FAIL；单测 test_a_rate_limited_answer_is_retried 用 Retry-After: 0 覆盖，不真 sleep |
| T2 的 10 个既有用例断言未改，新增 10 个（2 绿：全场景与 429 重试 + 5 红喂错数据 + 3 fixture 与守卫） | 垂直切片：每个新场景检查先有会红的用例，再让脚本通过 | uv run pytest -q tests/test_interview_smoke_script.py 读数为 20 passed、0 failed、0 skipped |

