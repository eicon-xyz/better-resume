# P13 问题台账

难题与坑，按发现顺序记；每条写「现象 → 根因 → 处置」。

## 1. 票据括注与现状不符：「打印报告 + usage」

- **现象**：T2 票括注真模型路径是「打印报告 + `usage`」，但 `interview_smoke.py` 基线就没有 usage 打印（usage 属 `real_model_smoke.py` 的 chat 流），interview REST 响应也不带 usage。
- **根因**：票据文字沿用了 real 层另一脚本的口径；执行方照「与现在一致」的正文约束保留现状并主动交代。
- **处置**：记为票据文字缺陷；是否给真模型路径补 usage 打印待用户拍板（见验收包 §8）。

## 2. 真模型路径三处未交代的回归（异家族评审抓出）

- **现象**：`--assert` 之外的真模型路径被换了登录身份（`m2-smoke-<hex>`）、上传文件名（`golden.pdf`），且 429 退避重试在该路径**静默**生效；两票交代表都只写了「仅 --assert」。
- **根因**：`run_user` 在断言开关之外生成、文件名取自场景名、retry 提示被 `if checks is not None` 包裹——声明范围 ⊊ 代码范围。
- **处置**：修复轮 F1 恢复基线身份与文件名（`m2-smoke` / `cv.pdf`）、retry 提示两种模式都打印；红-绿证据见验收包 §6。教训：**「保留原样」的承诺要落在会红的用例上**——现在有 `test_real_mode_keeps_the_baseline_identity_and_filename` 钉住。

## 3. 「落库」断言缺位 + 手测文档虚标

- **现象**：T4 红-绿切片 1 明文要求 `interview_sessions.resume_warnings` **落库**，实现只读 HTTP 响应（psql 仅失败诊断）；而 `MANUAL-TESTING.md` §1.5 第 10 项已把「落库」标成 e2e 已覆盖——写进了脚本里不存在的断言。
- **根因**：执行方把落库断言收窄为「HTTP 往返 + psql 写进用户清单」（在交代表里交代了，但按硬规则 3 这类收窄应先报用户）；T5 按票面语义标注时没回查断言实况。
- **处置**：修复轮 F2 给 `--assert` 成功路径补 DB 级断言（sessions 的 degraded_reasons/resume_warnings 落库、questions 行级 category 与追问继承；探针缺失显式 SKIPPED 不判失败）；F3 把 §1.5 第 9/10/11 项措辞改成与断言严格对应。残余小缺口见 §10。

## 4. 规格自相矛盾：「两种调用都被某一层跑到」 vs「不动 real 层」

- **现象**：T2 红线与 README §5③ 要求真模型/打印形态也被某一层跑到，但全仓只有 e2e 层引用 `interview_smoke`，real 层五步不含它；而 T2 的「不做」又禁止碰真机链路。README §1.2 自己写该脚本「不在任何 verify 层」，与 §1.3「real 层继续用」互相矛盾。
- **根因**：提案两处口径不一致，执行方按红线保守处理但未按「与 spec 冲突 → 停下来报」上报（两轴评审均点名）。
- **处置**：**待用户拍板**（验收包 §8 第 1 项）；推荐本阶段记为已声明偏差、另开后续票接进 real 层并计入调用预算。

## 5. 「证据落 var/evidence/<ts>-e2e/」看似无人实现

- **现象**：T4 验收要求证据落 `var/evidence/<ts>-e2e/`，脚本本身不写任何证据文件，`var/evidence/` 下也没有 e2e 目录——评审判为口径未兑现。
- **根因**：证据目录不是脚本的职责——`verify.sh` 的通用 runner 对每层都会建 `var/evidence/<utc>-<layer>/` 并把逐条命令输出 tee 进去（`scripts/verify.sh:317-333`）；e2e 层还没被跑过，所以目录还没出现。
- **处置**：口径澄清记入验收包；`bash scripts/verify.sh --layer e2e` 在宿主机跑通即落证据目录。AI 侧无需补实现。

## 6. 执行方自证的端到端读数没有留存产物，事后查库无痕

- **现象**：T4 执行方报「本地 uvicorn + 本地 fake + redis 实跑 exit=0、四场景 PASS、run_user=m2-smoke-1633dafe、连跑两次各 4 行」，但 `var/evidence/` 无产物，评审查唯一在跑的库（127.0.0.1:5433）`m2-%` 命中 0 行。
- **根因**：执行方收尾时按「共享状态自己还原」删掉了自己造的行（其收工回报有交代），读数只存在于文字；沙箱内也起不了 compose 栈，无第二方能复跑同口径。
- **处置**：该读数在验收包里单列为「执行方自证、无留存产物、未独立复跑」；权威 e2e 读数以你在宿主机的跑为准（Q3）。教训：**自证读数要么落盘、要么明说没落盘**——这次两者都做了，但「跑完清理」与「留证」天然冲突，口径要先说清。

## 7. 主验收方变异演示的恢复步骤拷错路径

- **现象**：T3 变异演示后，恢复 cp 把备份拷进了 `apps/api/scripts/verify.sh`（当时 cwd 已进 `apps/api`），根目录 `verify.sh` 停在变异态，守卫持续红。
- **根因**：恢复命令没用绝对路径；cp 静默成功，错在目标路径。
- **处置**：按 `cmp` 确认后删除误拷文件、绝对路径恢复（numstat 11/4 与 T3 回报一致、守卫复核 27/0/0/0）；此后所有变异演示的恢复一律绝对路径 + `cmp` 复核。红证据本身有效（变异确实生效过）。

## 8. 主验收方名下的两处记录不严谨

- **现象**：票据 Status 被翻成裸 `done`（不在 `docs/agents/triage-labels.md` 词表，且像「AI 自行宣布完成」）；共享简报写「票据均为纯追加」（忽略了 Status 行的 5 处删除）。
- **根因**：翻状态时没对 P11 先例（`done（红绿已过，待用户验收）`）；简报口径写得过粗。
- **处置**：五张票 Status 已补限定语；简报口径已改为「执行方零越界；正文纯追加 + 主验收方翻 Status 各 1 行」。

## 9. 手抄契约常量缺漂移守卫

- **现象**：`interview_smoke.py` 的 `MAX_FOLLOW_UP` / `LEGAL_CATEGORIES` / `DIMENSION_KEYS` / `MIN_SCORED_PER_CATEGORY` / `THIN_SAMPLE_COMMENT` 是契约手抄副本，只有降级码与 `NO_CATEGORY_MARKER` 有守卫。
- **根因**：脚本有意不 import 引擎（单文件可跑），副本与真源之间需要显式钉子。
- **处置**：修复轮 F5 新增 `test_contract_constants_match_the_engine`，用真源符号（签名默认值 / `QuestionCategory` / `DIMENSION_LABELS` 等）钉副本；主验收方变异 `MAX_FOLLOW_UP 2→3` 实测红。**残余**：测试文件自身的 `CATEGORIES/MAX_FOLLOW_UP/…` 副本未纳入守卫（修复轮明确没做，见验收包 §7）。

## 10. db 落库断言的 reasons 半边没有独立用例

- **现象**：把 `db: session degradation is persisted` 的 reasons 比较单独打成恒真，现有测试不红（那条用例喂的是 warnings 错、reasons 对，被 warnings 半边兜住）；两半都打恒真才红。
- **根因**：一条 `expect` 合并两个字段比较，用例只从 warnings 侧破。
- **处置**：检查整体「会红」成立（主验收方 B2 变异实测）；reasons 半边缺一条喂错 `degraded_reasons` 的用例，记为待补（一行测试）。

## 11. T4 的用例写进 T2 的测试文件（写入口径扩展）

- **现象**：T4 票声明的写入路径是「脚本与所需 fixture」，实际 10 个用例进了 T2 授权的 `test_interview_smoke_script.py`。
- **根因**：主验收方派工时按「一个脚本一个测试文件」扩了口径（评审记为口径冲突，非执行方越界）。
- **处置**：**待用户确认**（验收包 §8 第 2 项）；推荐接受并记为派工方口径扩展。

## 12. e2e 每跑一次留一套业务行，不清理

- **现象**：断言模式每次跑铸 1 用户 + 4 会话及其题目/答案行，脚本无清理逻辑。
- **根因**：唯一 run_user 隔离 + 「新建而非修改」的还原解读；T4 红线的「共享状态自己还原」原本针对改既有共享配置。
- **处置**：**待用户拍板**（验收包 §8 第 3 项）；compose 跑法末尾 `down -v` 整库清掉，推荐接受现状。

## 13. FakeStack 是「栈形状」的第二份实现

- **现象**：单测的 FakeStack 手写了 REST 响应的 JSON 形状，不 import `http/interview.py` 的 response_model。
- **根因**：站在 HTTP 边界测脚本（不 mock 内部模块）的必然代价；形状的真相只能由真栈跑暴露。
- **处置**：记为已声明局限（票据本就要求 FakeStack 站 HTTP 边界）；权威形状校验 = 你在宿主机的 e2e 跑。

## 14. 提案净结果句与交付有两处出入

- **现象**：README §1.4 净结果写「语义断言全部搬进 CI/nightly」，实际 e2e 层只接了手动（nightly 未接线）、第 9 项语义也没搬进 e2e。
- **根因**：提案的愿景句写在 Q1–Q4 拍板之前；T3 红线禁改 workflow 使 nightly 接线只能另开票。
- **处置**：记为与提案的偏差（验收包 §5）；nightly 接线列后续票候选（验收包 §8 第 6 项）。

## 15. README 顶部状态行过期

- **现象**：`docs/tickets/p13-golden-path-e2e/README.md:4` 仍写「状态：已规格化，**待用户点头**」。
- **根因**：用户已点头开工（本会话「接受任务」），状态行属票面既有正文，执行方与主验收方均无权改写 spec。
- **处置**：留待收口时随验收结论一并更新（硬规则 2：文档只描述当前状态）。

## 16. mtime 不能当写入归责的证据（两笔账）

- **现象一**：修复轮报告落盘后，`interview_smoke.py` 的 mtime 变成 21:25:58，异家族复核判「无法判定谁写的」。
- **根因**：主验收方的变异演示（改恒真→跑→cp 恢复）——恢复动作本身会重写文件、刷新 mtime，内容经 `cmp` 与备份一致。
- **现象二**：`apps/api/src/better_resume/ai_resilience/redis_buckets.py` 在 21:34:44 被摸过 mtime（同刻 `__pycache__` 重编译），但它不在任何人的写入声明里。
- **根因**：**未定位**。逐一重放 `--layer all` 全部 16 条命令（pytest/覆盖率/ruff/alembic/契约导出/脚本编译/审计核对）均不复现写入；`git hash-object` 与 `HEAD` 的 blob **逐字节一致**（`a5648bd8…`），零内容变化、无行为影响。时间上唯一吻合的候选是并行子代理的活动，但无日志可证。
- **处置**：两笔都如实入账。教训：**写入归责要看内容哈希与操作日志，mtime 只是弱证据**——变异演示的恢复、幂等重写、缓存重编译都会刷新它；评审拿 mtime 做越界判定时要把这三类噪声排掉。

## 17. 修复轮自述的四处轻微失真（异家族复核抓出）

- **现象**：① `probe_db_rows` 的「docker 可用但 sessions 行缺失→SKIPPED」边界没写进自述；② 中间用例计数 21→25→28 与章节叙述顺序不能同时为真；③ F5 红引文的断言操作数次序与用例正文相反；④ 自述「9 个 M」与自列 11 行相抵、mtime 时间戳与现值不符。
- **根因**：自述按演示顺序而非章节顺序写、引文凭记忆转写、计数凭印象——产物本身全对（复核逐条对上），失真全在「怎么说」。
- **处置**：① 的边界行为属实质问题，进微型修复轮 2 修正（SKIPPED 只留给真·无 docker，查得到库但缺行按 FAIL）；②③④ 记档不返工。教训同 P12 台账 §3：**自述里的每个数字与引文都要能被实测证伪**——这次靠异家族复核兜住了。

（§16 补记：该文件的 mtime 后续再次被幂等刷新，与工作区工具活动相关但重放任何单条命令都不复现；`git status --porcelain apps/api/src` 对全部源文件无输出——内容与索引逐字节一致是硬保证，mtime 归责不可行。）

## 18. 存量时序 flake：`test_bounded_wait_raises_a_clear_error`

- **现象**：`tests/test_distributed_lock.py::test_bounded_wait_raises_a_clear_error` 偶发红，失败形态是 `Failed: DID NOT RAISE QuestionLockTimeout`（第二次 acquire 没被挡）；单跑 3/3 绿、纯 pytest 全量 4 跑 0 红，`verify.sh --layer all`（带 `--cov`）若干跑 2 红。
- **根因**：与本阶段改动无关（锁模块零接触）。机制：持锁协程持锁期间锁键 TTL 过期（或 holder 异常提前释放），第二次 acquire 直接拿到锁；`--cov` 插桩拖慢事件循环，把时序窗口放大。测试本身依赖真实 Redis 与真实时间——违反本仓库「时间用注入时钟测」的做法。
- **处置**：记为存量 flake，不属 P13 范围；建议后续把该测试的 TTL/等待改成注入时钟（红-绿修复另开票）。收口读数里 `--layer all` 的红全部归因到它，其余 15 条命令与 980+ 用例全绿。

## 19. DB 落库探针从未工作过：psql 的 `-c` 不做变量插值

- **现象**：首次真栈 e2e 跑通（EXIT=0）但四场景的落库断言全部 `SKIPPED (docker/psql probe unavailable)`；栈明明健康。主验收方把探针拉起来实测：`psql -v sid=x -c "… WHERE id = :'sid'"` 报 `ERROR: syntax error at or near ":"`、returncode 1 → `_psql_query` 返回 None → SKIPPED。
- **根因**：psql 的 `-c` 命令串**不做变量插值**（`:'sid'` 只在 stdin/交互模式生效）。单测全部 monkeypatch 掉 `_psql_query`，所以单元层绿着；真库路径在验收包 §7.1-3 本来就挂着「未验证」——一验就是坏的。
- **处置**：微型修复轮 3 改经 stdin 喂 SQL（保留 `:'sid'` 防注入与全部 argv 不变量），红-绿 + 真栈实测证明；随后重跑 e2e 让落库断言真跑。教训：**挂「未验证」的探针代码要在收口前至少真跑一次**——伪造不出的 SKIPPED 标记这次立了功（D22 口径：宁可显式跳过，不许假绿）。
