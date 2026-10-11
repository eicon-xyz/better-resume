# P11 问题台账

难题与坑，按发现顺序记；每条写「现象 → 根因 → 处置」。

## 1. 语料文件被两个 worker 同时写

- **现象**：语料整理派出去后长时间没有产物，Lead 判定其已停并自己写了 `corpus/questions.json`（120 条 / 13 个中文汇总来源）；
  随后子代理回报完成，并按「唯一产物」指令**覆盖**成它自己的版本（120 条 / 43 个官方文档来源）。
- **根因**：同一路径被两个写入方拥有——「先建任务、再派活」只保证任务唯一，没有保证**在途期间的排他**。
- **处置**：保留子代理版本（来源更可复核），Lead 复核结构与配额（`check_corpus.py` + 随包语料用例）并逐个复核 43 个 URL
  （42 个 200，1 个域名抖动）。教训：`list_agents` 看不到 `subagent`，判断在途状态只能靠消息或产物。

## 2. 测试夹具的 CJK 分隔符被合成 PDF 字体抹掉

- **现象**：`build_resume_pdf()` 生成的简历里「技能特长」行解析后 `skills == ['n n n']`，依赖技能匹配的用例（语料过滤）全部走空匹配。
- **根因**：合成 PDF 的字体不保留「、」这类 CJK 标点的字形，文本层退化成 `n`；这是**夹具限制**，不是解析器缺陷
  （真实 PDF 的 CJK 文本层正常，既有用例的中文断言也都通过）。
- **处置**：新增 `build_matched_resume_pdf()`（ASCII 逗号分隔）供需要真实技能串的用例使用；既有夹具未改。

## 3. 「样本不足」在一行里渲染两次

- **现象**：报告「按类给分」一节里，计分题不足的类别显示「样本不足 样本不足」（分数格 + 评语格各一次）。
- **根因**：后端 `comment` 与前端分数占位用了同一个字面量。
- **处置**：前端在 `comment === THIN_SAMPLE` 时不再渲染评语格；报告页测试断言行内只出现一次。

## 4. 实现移位导致审计引证失效

- **现象**：`verify_audit_evidence.py --strict` 从 122/0/0 掉到 110/9/3（12 个 issue 部分或完全失证）。
- **根因**：改了被引用的文件（`report_service.py` / `question_service.py` / `orm.py` / `http/interview.py` /
  `sections.py` / `settings/config.py` 等），引证窗口随之下移。
- **处置**：一次性重锚脚本（复用校验器自身的 `EVIDENCE_PREFIX` / `norm` / `check_issue` 语义，只动「命中为 0」的引证）
  重锚 20 条 → `--strict` 回到 **122/0/0**，并重渲染 `docs/audit/MODULE-AUDIT.html`。脚本是一次性工具，未入库。

## 5. 分布式单飞用例偶发红

- **现象**：一次全量跑里 `tests/test_distributed_flight.py::test_waiter_takes_over_after_the_owner_dies` 失败；单独重跑通过。
- **根因**：未定位（该用例依赖 Redis 时序；本机 Redis/Postgres 是 compose 之外的独立一套）。与本次改动面无交集。
- **处置**：记录观察、不修（超出本阶段范围）；如复现按 `diagnosing-bugs` 先证伪再改。

## 6. 全量跑里一次未复现的红

- **现象**：一次全量跑里 `tests/interview_engine/test_question_service.py::test_vendor_failure_rolls_the_session_back_to_draft` 失败
  （`SessionNotFound`：读不到刚建的 session 行）。
- **根因**：未定位。同一文件单跑绿、随后两次全量跑也绿（944 passed），无法复现；`pytest` 未装 xdist/randomly，测试是顺序执行的。
- **处置**：如实记为 flake，不掩盖；若再复现按 `diagnosing-bugs` 先证伪再改。
