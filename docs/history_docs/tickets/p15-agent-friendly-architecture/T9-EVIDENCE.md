# T9 证据

## 意图复述

- 我理解这票解决什么：「下一张该动哪张票」现在只能靠人一次次说「继续」来推进；把它变成一条可复跑的命令输出，同时把票据头部结构的坏味道（缺 Status、Blocked by 悬空、同号重名）挡在动工之前。
- 我怎么做到文件粒度：新建 `scripts/ticket_frontier.sh` 一个 bash 文件，三个内部入口 `frontier()` / `check_tree()` / `selftest()`——只读票目录里 `T<N>-*.md` 头部 20 行内的 `Status:` 与 `Blocked by:`，按 `docs/agents/issue-tracker.md` 的 Frontier 规则排序取编号最小者并打印 `T<N> <文件名> <标题>`；`--check` 逐票扫三类结构错（缺 Status、阻塞指向不存在的票、同号重名）并点名文件；`--selftest` 在 `mktemp -d` 里现搭 1 棵合法树 + 3 棵非法树，自断言读数与预期一致。
- 我不做什么：不改任何票据文件（包括把已完工的票改成 resolved）、不动 `scripts/verify.sh` 接线、不引任何依赖（纯 bash）、不把 spec 三类之外的形态（缺 `Blocked by:` 行、Status 取值不在词表内、非 `T<N>-` 命名的文件）判成 `--check` 红。

## 验收口径原始输出

实现前（红）：脚本不存在，三条验收命令全部 127。

```bash
$ bash scripts/ticket_frontier.sh docs/tickets/p15-agent-friendly-architecture
exit=127
$ bash scripts/ticket_frontier.sh --check docs/tickets/p15-agent-friendly-architecture
exit=127
$ bash scripts/ticket_frontier.sh --selftest
exit=127
bash: scripts/ticket_frontier.sh: No such file or directory
```

实现后（绿），三条命令原样复跑：

```bash
$ bash scripts/ticket_frontier.sh docs/tickets/p15-agent-friendly-architecture
T1 T1-read-transcripts.md 读转录：用户如何给智能体转向
exit=0

$ bash scripts/ticket_frontier.sh --check docs/tickets/p15-agent-friendly-architecture
OK docs/tickets/p15-agent-friendly-architecture：结构校验通过（9 张票）
exit=0

$ bash scripts/ticket_frontier.sh --selftest
ok   frontier：跳过 resolved / claimed / 被未结题票阻塞，取 T4：T4 T4-free.md 四号票
ok   check：合法树退出码：0
ok   check：缺 Status 行退出码：1
ok   check：缺 Status 行点名文件与原因：yes
ok   check：Blocked by 悬空退出码：1
ok   check：Blocked by 悬空点名文件与票号：yes
ok   check：同号重名退出码：1
ok   check：同号重名点名两个文件：yes
selftest: 8 项断言，失败 0 项
exit=0
```

读数解读：frontier 落在 **T1** 而不是 T4——按 `docs/agents/issue-tracker.md` §Wayfinding 的字面规则
（未完成、无阻塞、未被认领、编号最小者优先），T1/T2 的 Status 仍是 `ready-for-agent`（工作已成文但未结题），
所以它们是合法 frontier；T3 已 `resolved`，T4–T7 排在 T1 后面，T8 被 T5/T6/T7 阻塞。
frontier 是「状态说了算」，要换结果只能改票的 Status 行，而改票不在本票权限内。

坏输入必红（临时树在 /tmp，断言同时进 `--selftest`；此处用真实文件核验点名）：

```bash
$ bash scripts/ticket_frontier.sh --check <树>/no-status
<树>/no-status/T2-x.md: 缺 Status 行
exit=1

$ bash scripts/ticket_frontier.sh --check <树>/dangling-blocker
<树>/dangling-blocker/T1-y.md: Blocked by 指向不存在的票 T42
exit=1

$ bash scripts/ticket_frontier.sh --check <树>/dup
<树>/dup/T3-b.md: 同号重名：与 T3-a.md 同为 T3
exit=1

$ bash scripts/ticket_frontier.sh <树>/all-done   # 全结题或已认领 → 无 frontier
exit=0（stdout 空）

$ bash scripts/ticket_frontier.sh /tmp/does-not-exist
票目录不存在：/tmp/does-not-exist
exit=2
```

## 实现决定交代

| spec 未覆盖、我自行拍定的决定 | 为什么这么拍 | 我明确没做的 |
| --- | --- | --- |
| 「未完成」= Status 不在 `{resolved, wontfix}`；「已认领」= Status 恰为 `claimed` | issue-tracker 只写「未完成/未被认领」，没给终态词表；`resolved` 是结题、`wontfix` 是「不做」，都不该再被推成下一步，`claimed` 是 §认领 里唯一的认领写法 | 没把 `needs-triage`/`needs-info`/`ready-for-human` 从 frontier 里滤掉——规则里没有这条，滤掉就是自创 |
| 「靠近顶部」= 文件前 20 行（`HEAD_LINES` 常量） | 规则没给行数；票样的 `Status:`/`Blocked by:` 都在第 3–7 行，20 行足够，又能躲开正文/评论区里的同名文本 | 没做行数配置项，真要改就改常量 |
| 缺 `Blocked by:` 行按「无阻塞」处理，不算结构错 | `--check` 的三类错是票里点名的闭集，加第四类会把原本能跑的树判红；规则「列出的票据全部完成后才可开工」对空列表天然成立 | 没校验 Status 取值是否在 triage 词表内、没校验 `Type:` 行、没要求 `Blocked by:` 必填 |
| Blocked by 指向不存在的票时，frontier 把它当「有阻塞」跳过 | 指向不存在的票就无从判定它完成，按保守方向处理；`--check` 已经专门点名这种树 | 没让 frontier 因悬空阻塞直接报错退出（frontier 是读，闸门在 `--check`） |
| `T<N>-EVIDENCE.md` 不算票 | 它与票据同前缀同后缀，不过滤会把每张票同时判成「同号重名 + 缺 Status」——第一次实跑就是被这个打红的 | 没把 `ACCEPTANCE.md`/`PROBLEMS.md` 之类的名字硬编码进过滤（它们本就不匹配 `T<N>-*.md`） |
| 目录不存在退 2；无 frontier（全结题/已认领）空输出退 0 | 前者是调用方给错路径，不是结构红；后者是合法状态，不是错误 | 没给「无 frontier」加哨兵文案，stdout 保持可直接喂给下一条命令 |
| `--selftest` 的 4 棵样本树在 `mktemp -d` 里现场生成，断言退出码 + 点名内容 | 红线要求只读真实票目录、不加依赖，样本内嵌是唯一不往仓库落 fixture 的写法 | 没在仓库里建 fixture 目录（那会多出一个写入路径），也没引入 bats 之类的测试框架 |

与提案的偏差：无。唯一写入路径 `scripts/ticket_frontier.sh` 之外只动了本文件两段（issue-tracker §验收包 明确不计入写入路径）。
