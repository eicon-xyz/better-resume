# P9 两轴评审（阶段 4）

> 基点：`main...HEAD`（`fd79375...e1ff440` 起的三提交）。两轴**分开跑、并列呈现、不合并、不重排**（仓库约定：`docs/agents/subagents.md` §5）。
> 两个子代理各自独立上下文；Standards 轴读 `CODING_STANDARDS.md`/`AGENTS.md`/`docs/agents/*` ＋ Fowler 坏味道基线；Spec 轴读 `docs/tickets/p9-verify-map-truth/README.md`。
> **注意**：Standards 轴读的是提交 `fa65fa4` 的修订，其引用的行号在收口提交后可能已漂移（下文按结论处理，行号以最终 HEAD 为准）。

## Standards 轴

### 硬违规（对照成文规范）

| # | 位置 | 规范 | 处置 |
| --- | --- | --- | --- |
| 1 | `README.md` 缺「预估」段 | `docs/agents/issue-tracker.md:9`「固定六段：…／预估／…」 | ✅ **已修**：补 §8.5 预估（预估 vs 实际对照表） |
| 2 | `README.md` 承诺新建票目录的 `PROBLEMS.md`，实际写进了 `p1-post-v/PROBLEMS.md` | `issue-tracker.md:15`（证据类产物）＋「列了却没交付」本身破坏验收 | ✅ **已修**：把交付物表与控制点改成真实落点，并在 `ACCEPTANCE.md` §5.5 记偏差与理由（P44 与 P31 同表才有对比价值） |
| 3 | `README.md` 头写「待你点头」，而分支已含实现 | `issue-tracker.md:26-33`「spec 必须先经用户明确确认才动工」 | ✅ **已修**：状态改为「已拍板并实施完毕（A2/B1/C1）」，并注明本文件保留为提案原文、不事后改写 |

### 坏味道（判断项）

| # | 味道 | 引用 | 处置 |
| --- | --- | --- | --- |
| 1 | **Middle Man**：`build_deploy(){ add_deploy; }` 等 5 个纯转发 | `verify.sh` 旧 :159-163 | ✅ **已修**：删掉 5 个转发层，层构建器即真实定义（`build_deploy/build_fault/build_soak/build_real/build_scripts`） |
| 2 | **重复分派**：`build_layer()` 的九路 case 与 `LAYER_ORDER` 重复 | `verify.sh` 旧 :222-234（而 :185 已有 `build_$layer` 的名字派生分派） | ✅ **已修**：`$LAYER` 在上面校验过，改为直接 `build_$LAYER`（不再有第二份层名单） |
| 3 | **Duplicated Code**：`LAYER_ORDER`/`ALL_PARTS`/case 三处层名单；`build_all` 的展开顺序无守卫 | `verify.sh:177,178,217` | ⚠️ **部分接受**：『all 的顺序会无声漂移』**不成立**——`test_the_coverage_floor_runs_after_the_pytest_that_writes_its_data` 正好钉的就是唯一有顺序语义的那一对（写数据 → 判底线）；其余顺序无语义。其余两处重复已随 #2 收敛 |
| 4 | **Primitive Obsession**：层名是裸字符串（≥4 处） | `verify.sh`、`test_verify_script.py:132` | ⚪ **不改**：bash 里为「层名」造类型只会加一层间接；真正的守卫是「`--list` 的层头 == 脚本接受的层」这条相等断言（已有） |

### 另一条（Spec 轴提出、Standards 未提，同属结构判断）

| 味道 | 引用 | 处置 |
| --- | --- | --- |
| **逐字同源未做到**：相等断言用 `set()`，顺序与重复不可见 | `test_verify_script.py` 旧 :146 | ✅ **已修**：改为列表逐字比较（顺序 + 重复都算），并在 docstring 写明「verbatim means order and duplicates count too」 |

## Spec 轴

### (a) 缺失或未完成

| # | 规格行 | 处置 |
| --- | --- | --- |
| 1 | §5/§6.1 要求 `docs/tickets/p9-verify-map-truth/ACCEPTANCE.md`（红绿原始输出、未验证项、偏差）；评审时目录里只有 README | ✅ **已补**：`ACCEPTANCE.md` 已落（含新鲜复现的红：**stash 新脚本、留新测试** → 7 failed；以及最终收口读数） |
| 2 | §3.1 要求「`--list` 每一行与 `--dry-run` 每一行**逐字相同**」 | ✅ **已修**：见上（列表比较）；另有附带的逐字改进——`soak` 的 `mkdir` 与 `--json` 现在用**已展开**的变量值渲染（`verify.sh` 顶部展开一次），地图与 dry-run 是同一串字符 |
| 3 | §3.5.2 要求新建票目录的 `PROBLEMS.md` | ✅ 记录偏差（同 Standards #2） |

### (b) 未被要求的行为（scope creep）

| # | 行为 | 处置 |
| --- | --- | --- |
| 1 | `--list` 强制 `SCOPE=all`（地图忽略 `--scope`），规格未授权 | ⚪ **保留 + 补测**：这是「地图不能因无关开关缺层」的有意选择（否则读者问「all 到底跑什么」会看到被 scope 塑形的地图）；Spec 轴的顾虑（地图与**带 scope 的展开**天然不同）成立，故新增 `test_the_list_map_shows_the_full_plan_even_when_a_scope_is_given` 把它钉成规范而非暗行为，并写进 `ACCEPTANCE.md` §4.4 未验证项（地图与带 scope 展开的差异本身不做断言） |
| 2 | 地图里的散文行、`--dry-run` 前缀由两空格缩进改为 `$ ` | ⚪ **接受**：散文行是地图的可读性所需（测试只比对 `api:/web:/all:` 命令行）；前缀改动在 diff 内自洽（Standards 轴亦确认） |

### (c) 实现了但看着不对

**无。** Spec 轴自行复跑了 CLI 断言：`--list` 九个层头齐（含 `coverage:`）＋ `real` 五步；`--layer coverage --scope web` → `nothing to run`（rc 0）；其余 `层×scope` 展开与 `main` 逐字相同。

## 一行总结

- **Standards**：3 条硬违规（全部已修）＋ 4 条坏味道（2 修 / 1 部分接受 / 1 不改）；最重的是**提案文件承诺了没交付的产物**。
- **Spec**：3 条缺失（2 已补、1 记偏差）＋ 2 条越界（1 补测转正、1 接受）；**无「实现错了」项**。
- 两轴唯一重叠的发现是「逐字 vs 集合」——已按更严的一侧（逐字）收敛。

