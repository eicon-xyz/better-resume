# p15 Standards 轴评审报告（固定点 HEAD b09bbd2，2026-10-17）

评审面 = p15 各票「唯一写入路径」声明范围内的改动（以各票 EVIDENCE 改动清单为权威）；p14 在飞改动只标注不评。
方法：读 CODING_STANDARDS.md / AGENTS.md 三节 / docs/agents/subagents.md §8.2–§8.5 与 /root/.dsh/skills/code-review/SKILL.md 的 smell baseline；逐票核票头「唯一写入路径」与 git diff --numstat；复跑 `bash scripts/verify_write_scope.sh --check docs/tickets/p15-agent-friendly-architecture`（越界 9 = DECISIONS/HANDOFF/agents×3/design refs×4，与 T24-EVIDENCE「越界 9 = 用户 p14 在飞自有改动」及各文件 mtime 相符，非 p15 票越界）。工具已拦下的（ruff/eslint/pytest/verify.sh --layer scripts 当前全绿）不重复报。

## Findings

### S1 major · docs/tickets/p15-agent-friendly-architecture/T26-rule-pointers.md:3 · 写入路径声明与实际写入面不符
票头声明「唯一写入路径: `AGENTS.md` 与 `CODING_STANDARDS.md`」，但该票落地内容包含 T12 引入的技能文档刷新——skills/modules/llm_gateway/SKILL.md:10-11 的 is_configured→config_status 段改写被记入 docs/tickets/p15-agent-friendly-architecture/PROBLEMS.md:38「去处：并入 T18 的 skills 写入面」，而 T18 的声明是「scripts/ + skills/（create-verification-skill 产出目录）」；skills/modules/llm_gateway/SKILL.md 不在两张票任一声明的字面范围内（T18 声明括号内限定为「create-verification-skill 产出的交付验证技能目录」）。该文件实际被改（git diff 可见），按 verify_write_scope 的「只认字面 token、不做模糊猜测」口径属字面越界，被「阶段并集模式」掩盖的原因恰是 T18 声明里 skills/ 这个宽 token。为什么违规：subagents.md §8.3「不许扩大写入路径」+ §8.2 唯一写入路径栏；写入面超出票头字面声明而未在 EVIDENCE 的写入路径比对里点名（T18-EVIDENCE.md:115 的清单未列该文件）。

### S2 major · docs/tickets/p15-agent-friendly-architecture/T5-EVIDENCE.md（对照 T5-secrets-gate.md:4 / T6:4 / T7:4）· 票据状态与事实不符
T5/T6/T7 三票 Status 仍为 claimed，但对应交付物（scripts/verify_secrets.sh、verify_docs_hygiene.sh、verify_citations.sh）均已落地且被 T8（Status: resolved，Blocked by T5,T6,T7）接进 verify.sh --layer scripts 并全绿，T24/T25/T26 等下游票也按「已落地」引用了这些脚本。按 docs/agents/issue-tracker.md:93-97 的 Status 语义（claimed=认领中、resolved=结题），三票的状态行与台账事实矛盾——frontier（ticket_frontier.sh --check）据此会漏报/误报下一张可开工票。为什么违规：建议 1 的目标就是「票据状态成为唯一进度源」，状态行失真是本阶段自己定义的红线类问题（属流程/台账面，非代码）。

### S3 minor · scripts/verify_write_scope.sh:15-17（豁免段）· 豁免范围宽于 §8.3 授权
脚本把「被检查阶段目录里的 T<N>-*.md 与 PROBLEMS.md」整体豁免出越界判定。subagents.md §8.3 只授权「执行方自己那两段自述追加进 T<N>-EVIDENCE.md 末尾」不计入写入路径；票正文其余部分（五栏、Status、Answer）被票面红线明令不许改（如 T24 红线「不改票据文件」）。T24-EVIDENCE.md:15 自己交代了这一残留（「那一半由 §8.7 的 sha256 基线负责」），属已知取舍而非隐瞒；但结果是把「执行方偷改票面规格」从本工具的可判范围里整体拿掉，而 §8.7 基线在本阶段并未实际建立（var/ 下无 pre-dispatch.sha256 快照可核）。判断项：工具口径与规范授权范围的偏差已披露、补偿机制缺位未披露于票面。

### S4 minor · skills/verify-delivery/__pycache__/ · 临时产物落在唯一写入路径的技能目录内
check_copy.py 运行产生的 __pycache__（.pyc 文件）留在了 skills/verify-delivery/ 下。.gitignore:2 的 __pycache__/ 规则可挡提交，不构成仓库污染，但 AGENTS.md「清洁度：不留临时文件」针对的是工作区状态；属一删了之的残留（rn -r 即可），不计为硬违规。

### S5 nit · docs/agents/issue-tracker.md:22-41 · 改动归属未标注（评审面判定项）
issue-tracker.md 的「意图复述/实现决定交代改写入证据文件」两段改动（git diff 5 行）未见于任何一张 p15 票的写入路径声明（最接近的 T26 声明只含 AGENTS.md/CODING_STANDARDS.md）。内容本身与 docs/tickets/p15-agent-friendly-architecture/T11-EVIDENCE.md:102、T24-EVIDENCE.md:15 的口径引用一致，像出票方的流程同步而非执行方越界；但按 T24 自建的门禁口径（工作区 diff 必须能归属到某张票的声明），这 5 行与 docs/agents/subagents.md:87 的同主题 1 行改动同属「无票声明、疑似出票方亲笔」。若确系规划方机械核对类动作，建议在 p15 README 或收口票据补一行归属说明，否则阶段并集读数里它们会长期挂在「越界 9」之外的第二类无主改动上。

### S6 nit · docs/tickets/p15-agent-friendly-architecture/T16-EVIDENCE.md:128 / apps/api/src/better_resume/ai_resilience/wait.py:11 · 新增抽象暂无产品侧调用方（possible Speculative Generality，heuristic）
wait_until 原语目前只被测试与新增用例调用，产品侧 RedisFlight.execute 未接入（T16-EVIDENCE.md:128 已如实记录「若将来要收敛需另立票」）。CODING_STANDARDS.md §6 第 2 条要求「新增抽象要有一个会变红的检查钉住」——钉住它的检查是 test_wait.py 与契约测试对原语自身的覆盖，满足字面；但「为将来收敛预留的产品级原语」形态在 Fowler baseline 里对应 Speculative Generality，按 §3 口径标注为 possible，非硬违规。T16-EVIDENCE 的披露已使风险可控。

## 明确检查过、未发现违规的面

- WS 语义：paraformer_rt.py:268 成功路径显式 close(1000)（T14 最小修正，符合 AGENTS.md WS 转写条款）；xunfei_ast.py:239/299 的 close() 无码与缺 close_timeout/proxy 是 T14-EVIDENCE.md:184 与 PROBLEMS.md P15-4 已如实登记的残余（无注入缝、未验证不虚报），未发现瞒报。
- 缓存语义：T13 写路径失效（resolver.bind / invalidate_hot_state）落地；跨副本仍靠 TTL（resolver 5s、热层 600s）收敛，AGENTS.md 缓存条款是「TTL 或写路径失效」二选一，合规；docs/tickets/p15-agent-friendly-architecture/T13-EVIDENCE.md:174 对未做 pub/sub 的取舍有交代。
- 错误语义：T23 FlowStateMissing→500 带 kind 字段，main.py:199-210 的 docstring 明确论证了为何不是 401/404/503+Retry-After，符合「响应能区分你没登录/我这边坏了/数据缺失」。
- 连接参数：paraformer open_connection 显式参数未回退；新增 httpx/ws 客户端未见裸默认。
- 语言与历史叙事：抽读各 EVIDENCE 决定表与新增脚本注释，未发现历史叙事式表述（禁词集命中为零）；verify_docs_hygiene.sh 全树绿背书。
- 凭据：抽扫各票据与脚本，无密钥形状命中（verify_secrets.sh 绿背书）。
- 依赖纪律：无新增第三方依赖（新增脚本全标准库；wait.py 仅用标准库）。
- 测试纪律：真实 sleep 残留点全部带「允许：」逐条理由（T16 口径），未见无理由的真实 sleep 断言；新增契约测试 test_adapter_contract.py 每条契约有坏 fake 自证（D22 口径）。
- 共享状态：场景绑定/热层用例由 T13/T16 的隔离库与 fixture 还原（PROBLEMS.md P15-1 已归档），未发现「全量绿单跑红」的已知残留。
- p14 在飞（不评）：docs/DECISIONS.md、docs/HANDOFF.md、docs/agents/domain.md、docs/design/refs/**、apps/web 的 AppShell/InterviewIntroPage/tokens.css 等大改动均属 p14 在飞面，未纳入 findings。

## 未覆盖的面

- apps/web 的 p14 在飞页面内部实现质量（不在评审面）。
- pytest/vitest 全量复跑（工具层全绿由派活方背书，本轴未重跑隔离库全量）。
- T17/T22 的 341 条审计引证逐字语义复核（T22-EVIDENCE 抽样 38 条的读数未逐条重验）。
- /root/.dsh/skills/code-review/SKILL.md 全文（沙箱外路径，仅按任务说明引用其 smell baseline 清单）。

## 自述与 diff 的核对方式

- 以各票头「唯一写入路径」字面 token 对 git diff --numstat 逐文件归属（等价于单票模式）；S1 即由此得出。
- 复跑 verify_write_scope.sh --check（阶段并集）与各门禁 --selftest（pr_state.sh、ticket_frontier.sh、verify_write_scope.sh 均 PASS）交叉验证读数。
- 各票 EVIDENCE 声称的「没做什么」逐条与 diff 比对（如 T13 声称未动 http/interview.py 失效调用点→diff 确认删除；T14 声称只改 paraformer 收尾一行→diff 确认为 1 行注释+close(1000)）。
- 票据文件改动以 git status（untracked 目录）+ 内容交叉引用核对，无 sha256 基线可用（S3 的补偿缺位）。
