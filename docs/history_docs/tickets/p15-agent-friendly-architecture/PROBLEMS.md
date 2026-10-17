# p15 难题台账

按 AGENTS.md 闸门 3「难题即时记」。每条 = 现象 / 根因归属 / 去处。

## P15-1 测试共享状态不还原，读数随跑随漂

- 现象：同一 `test_restore_report.py` 连续/并行重跑，红灯集合漂移（2 红 → 1 不同红 → 10/10 全绿）；并行 pytest 共享同一 Postgres 时出现 DeadlockDetected、relation 不存在。
- 归属：违反 AGENTS.md「测试的共享状态自己还原」；P07/P12 类在 p15 流程自身复现（T12/T13/T14 并行期）。
- 去处：T16 票面（测试 hermetic/共享状态 fixture 还原）；权威全量读数一律在新鲜/隔离库上取（T12 已实践 `br_t12_verify` 独立库）。

## P15-2 RestoreService.restore 读路径写库

- 现象：无题会话 restore 会派生并写 `interview_flow_state`，随后 QuestionService.initialize 主键冲突。
- 归属：读取路径写库的独立产品缺陷（T13 顺带发现，超出其红线）。
- 去处：T19 票（待派）。

## P15-3 门禁接线本身无会红的断言

- 现象：从 `build_scripts()` 删掉一条门禁接线行，`--list` 与 `--dry-run` 仍相等（一致性测试管不到「在不在」）。
- 归属：建议 7 的自检口径未覆盖「接线存在性」。
- 去处：T17 验收或评审定夺补断言。

## P15-4 xunfei AST 适配器无注入缝

- 现象：契约 2/3（close(1000)、连接参数显式）对 xunfei 覆盖不到，要真凭据+真网络。
- 归属：建议 6 已知残余；改构造签名=改对外行为，超出 T14 红线。
- 去处：评审清单；若用户点头再立票。

## P15-5 写范围重叠（流程自伤）

- 现象：T12/T13 同碰 `llm_gateway/resolver.py`，并行 pytest 互踩。
- 归属：出票方拆票粒度（两张票同圈 `apps/api/`），非执行方问题。
- 去处：retro 阶段落回 `docs/agents/subagents.md`（写路径必须文件级；共享库的测试要独立库）。
## P15-6 模块 SKILL.md 语义过期

- 现象：`skills/modules/llm_gateway/SKILL.md` 仍写「is_configured 是 async」，T12 已把该钩子改为 `config_status` 快照。
- 归属：实现与技能文档漂移（P06/P08 类）。
- 去处：并入 T18 的 skills 写入面（skills 索引另由生成脚本刷新）。
## P15-7 --strict 弱匹配兜住过期窗口

- 现象：逐字级门禁只要求窗口内命中 ≥1 条摘录，弱摘录（`)`、`name`、`...`）能让语义已漂移的窗口判绿（例：LG-09 引 resolver.py:236-241 现为 views() 的 status 段）。
- 归属：verify_audit_evidence.py 的匹配强度不足（D22「判定必须真判定」的深水区）。
- 去处：retro/评审权衡；若做，属验证工具自身强化票。
## P15-8 P45 构建出口在 compose v5 上失效

- 现象：Docker Compose v5.6.0 二进制里 `COMPOSE_BAKE` 零命中，`export COMPOSE_BAKE=false` 出口失效；buildx 0.37.2 的 bake 同意闸门恒拒 `network: host`，`--build` 一律 exit 1，三个构建栈脚本同受影响。
- 归属：环境升级导致的既有规避措施过期（非本轮引入）。
- 去处：T21（原型定修复方向：`--allow=network.host` vs `build.network: default`，择不削弱运行面者）。
