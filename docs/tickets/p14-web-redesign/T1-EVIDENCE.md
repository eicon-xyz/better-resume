# P14-T1 验收包 — 守卫闸门①②④ + 存量违规清零

- 票据：docs/tickets/p14-web-redesign/T1-style-guards.md
- 依据：docs/tickets/p14-web-redesign/README.md §1.2 / §1.3 / §4.1 / §4.3；D22 / D25
- 状态：待用户验收（AI 不自行宣布完成）

## 一、意图复述

本票只做「基建批」的样式守卫，不碰页面版式重修：

1. 把三条可机器判定的守卫做成会红的闸门，并接进 scripts/verify.sh 的 web 契约层：
   - 守卫① token 零假变量：CSS 引用的每个 --br-* 都有定义；--br-color-* / --br-gradient-* / --br-shadow-* 在 :root 定义的，必须在 prefers-color-scheme: dark 块重述。
   - 守卫② 页面 CSS 零裸 hex/px/rgb()/hsla()：扫描 styles/tokens.css 以外的全部 .css；放行只认违规行上一行的 /* allow: 理由 */。
   - 守卫④ 所有动画有 prefers-reduced-motion 处理：同文件 @media (prefers-reduced-motion: reduce) 内同选择器重访（animation: none 或任意 animation* 覆盖都算）。
2. 把存量违规清到零，使守卫进 CI 即绿。
3. 交出可复跑命令 + 原始读数 + 未验证项 + 与提案的偏差。

不做：守卫③（断点存在性）与守卫⑤（原生控件禁用）属 T3；不做守卫可视化报告；不动 JS/TSX、REST 契约，也不动 apps/web/src/api、audio、stream。

## 二、实现决定交代

### 2.1 假变量处置（票面拍死口径，无第三种）

| 引用文件 | 引用写法（清除前） | 处置 |
| --- | --- | --- |
| AiSettingsPage.module.css | var(--br-text-muted, #666) | 改 var(--br-color-text-muted) |
| AiSettingsPage.module.css | var(--br-border, #e5e7eb) | 改 var(--br-color-border) |
| AiSettingsPage.module.css | var(--br-text-muted, #6b7280) | 改 var(--br-color-text-muted) |
| InterviewRoomPage.module.css | var(--br-color-warning-bg, rgba(...)) | 改 var(--br-color-warning-bg) |
| ResumePreviewCard.module.css | var(--br-color-warning, #d97706) | 改 var(--br-color-warning) |
| ResumePreviewCard.module.css | var(--br-color-warning-bg, rgba(...)) | 改 var(--br-color-warning-bg) |

为什么这么清：fallback 让页面照常渲染而 token 实际不存在，是隐蔽漂移；warning 语义是「警示边/警示背景」，票面要求补真定义而不是继续用兜底色。

### 2.2 warning token 取值

tokens.css :root 增 --br-color-warning: #b45309、--br-color-warning-bg: #fdf3e3；prefers-color-scheme: dark 增 --br-color-warning: #f0b34e、--br-color-warning-bg: #3a2f18。
判断：amber 系；浅色主色取原兜底 #d97706 同色族的深一档，深色主色亮度与既有 --br-color-danger（#ff8b80）、--br-color-success（#63d29a）同档；背景对应既有 danger-surface 的琥珀版（浅色 #fdeceb→#fdf3e3，深色 #3a2020→#3a2f18），保持与 success/danger 同一档克制。

### 2.3 shadow 深色定义（唯一越出 warning 的 token 改动）

--br-shadow-sm / --br-shadow-md 按深浅双定义规则在 dark 块定义：
--br-shadow-sm: 0 1px 2px rgb(0 0 0 / 45%)；--br-shadow-md: 0 6px 20px rgb(0 0 0 / 55%)。
未改浅色值，未动其他 token。见 §五偏差 1。

### 2.4 守卫②清理口径

- 能映射到既有 token 的一律映射：间距类（gap/padding/margin）→ --br-space-*；字号 → --br-text-*；语义颜色 → --br-color-*。
- 组件几何/画布尺寸类保留原值，在“违规行上一行”写 /* allow: 具体几何 */。
- 不新增 token（warning 对除外），不删规则或选择器，不改 JSX。

| 类别 | 处置 | 例 |
| --- | --- | --- |
| 16px gap / 24px padding | 映射 | --br-space-4 / --br-space-5 |
| 13px、14px 字号 | 映射 | --br-text-sm（13px→14px 为派活交接包口径的近似映射，已经用户确认） |
| 12px 字号 | 映射 | --br-text-xs |
| 20px 字号 | 映射 | --br-text-lg |
| #15803d / #b45309 / #b91c1c | 映射语义色 | --br-color-success / --br-color-warning / --br-color-danger |
| 8px 6px 表格内边距 | 各边映射 | 8px→--br-space-2；6px→--br-space-1（近似） |
| 2px 徽章纵向内边距 | 映射 | --br-space-1（近似） |
| 1px 发丝边框/分隔线 | allow | 按钮/卡片/表格/气泡等，token 集无边框宽尺寸 |
| 8/1.5px 折叠箭头 | allow | 三角形几何 |
| 12/2px spinner | allow | 环径与环线宽 |
| 96px 拖拽区最小高、1px 隐藏文件输入、6px 进度条高 | allow | 组件几何 |
| 260px 侧栏 / 720px 气泡 / 960px 内容宽 | allow | 版式固定宽度 |
| 24/32/40/48/72px 各列 min-width | allow | 表格与列表列宽几何 |
| 260px 雷达画布、9px 轴标签 | allow | 画布尺寸与随画布缩放的标签字号 |
| 3px 警示条边框、2px 焦点外框与偏移 | allow | 几何 |
| 8px 光标宽、2px 光标间距 | allow | 光标块几何 |

### 2.5 两个需要点名的判断

- InterviewReportPage.module.css 的综合分 42px：超出 --br-text-* 字阶（最大 26px），硬映射会破坏报告页 hero 层次，故按「展示型一次性字号」allow，理由写进注释，留 §五偏差 2 请用户裁定。
- AiSettingsPage.module.css 的 6px（表格内边距与标签右距）与 2px（徽章纵向内边距）无对应 token，取最近的 --br-space-1（4px）；属派活交接包口径「近似映射允许」（已经用户确认），见 §五偏差 3。

### 2.6 守卫、测试与接线

- 守卫实现：scripts/check_web_style_guards.py 按票面规则形状实现三条守卫；CLI 逐行输出 <文件>:<行>: G<n> 说明，全绿末行 check_web_style_guards: ok，违规 exit 1，坏 root exit 2。
- 守卫测试：apps/api/tests/test_web_style_guards.py 共 8 例，全部从 CLI 断言（构造输入树 7 例 + 真树 1 例）。三类坏输入各报错且退出码非 0：G1 假变量、G2 裸 hex/px、G4 缺 reduced-motion；另含 G1b 深色缺定义、allow 上一行放行、allow 同行尾注不放行、G4 被覆盖。
- 接线：scripts/verify.sh 的 add_web_contract 增 python3 scripts/check_web_style_guards.py；build_scripts 的 pytest 清单增 tests/test_web_style_guards.py。
- 守卫测试文件按仓库 ruff 规则格式化（ruff format --check . 全绿：268 files already formatted）。

### 2.7 变异证明思路

删掉 apps/web/src/pages/chat/MessageBubble.module.css 的 prefers-reduced-motion 覆盖 → 真树守卫红 → 恢复；退出码与 sha256/逐字节比较见 §三.7。

## 三、可复跑命令 + 原始输出 + 数字

统一环境（每条命令前执行）：

~~~bash
export PATH="$HOME/.local/bin:$PATH"
export UV_CACHE_DIR="/root/better resume/.cache/uv"
export BR_DATABASE_URL="postgresql+asyncpg://better_resume:better_resume@127.0.0.1:5433/better_resume"
export BR_REDIS_URL="redis://127.0.0.1:6379/0"
~~~

### 3.1 守卫脚本（从仓库根跑）

~~~text
$ python3 scripts/check_web_style_guards.py
check_web_style_guards: ok (21 css file(s) under /root/better resume/apps/web/src)
EXIT=0
~~~

数字：退出码 0；扫描 21 个 .css；违规 0 条（清零前实测 72 条：G1 假变量 6 + G1b 深色缺定义 2 + G2 裸值 63 + G4 动画 1）。

### 3.2 守卫测试（--junitxml 读数）

~~~text
$ rm -f /tmp/t1-guards.xml
$ cd apps/api && uv run pytest tests/test_web_style_guards.py -q --junitxml=/tmp/t1-guards.xml
........                                                                 [100%]
JUNIT tests=8 failures=0 errors=0 skipped=0
（省略 pytest 共享 warnings 摘要）
~~~

数字：8 例、0 失败、0 错误、0 跳过；满足例数 ≥7。三类坏输入各报错且退出码非 0 的用例：test_a_referenced_but_undefined_token_is_reported（G1）、test_bare_hex_and_px_literals_are_reported（G2）、test_an_animation_without_reduced_motion_is_reported（G4）。

### 3.3 verify 脚本层图钉测试

~~~text
$ cd apps/api && uv run pytest tests/test_verify_script.py -q
...........................                                              [100%]
27 passed, 2 warnings in 4.85s
~~~

数字：27 例全绿；--list 与 --dry-run 逐条相等、coverage 顺序、scope 行为等层图钉断言未破。

### 3.4 层计划与展开一致

~~~text
$ bash scripts/verify.sh --list   （contract / scripts 两段摘录）
contract:
  web: pnpm -C apps/web lint
  web: pnpm -C apps/web typecheck
  web: pnpm -C apps/web check:api
  web: python3 scripts/check_web_style_guards.py
scripts:
  api: cd apps/api && uv run pytest tests/test_fault_probe.py tests/test_drill_prereqs.py tests/test_load_test_script.py tests/test_real_model_smoke_script.py tests/test_verify_script.py tests/test_web_style_guards.py
  all: for f in scripts/*.sh; do bash -n "$f" || exit 1; done; echo "shell syntax ok"
  all: uv run --project apps/api python scripts/check_scripts.py
  all: uv run --project apps/api python scripts/verify_audit_evidence.py --structural

$ bash scripts/verify.sh --layer contract --scope web --dry-run
DRY RUN -- layer=contract scope=web
  $ pnpm -C apps/web lint
  $ pnpm -C apps/web typecheck
  $ pnpm -C apps/web check:api
  $ python3 scripts/check_web_style_guards.py

$ bash scripts/verify.sh --layer scripts --dry-run
DRY RUN -- layer=scripts scope=all
  $ cd apps/api && uv run pytest tests/test_fault_probe.py tests/test_drill_prereqs.py tests/test_load_test_script.py tests/test_real_model_smoke_script.py tests/test_verify_script.py tests/test_web_style_guards.py
  $ for f in scripts/*.sh; do bash -n "$f" || exit 1; done; echo "shell syntax ok"
  $ uv run --project apps/api python scripts/check_scripts.py
  $ uv run --project apps/api python scripts/verify_audit_evidence.py --structural
~~~

数字：contract web 展开 4 条、scripts 展开 4 条，均与 --list 逐条相同；由 3.3 的逐条相等断言钉住。

### 3.5 verify --layer all

~~~text
$ bash scripts/verify.sh --layer all
[3/17] pnpm -C apps/web exec vitest run → 25 passed (25) / 183 passed (183)
[4/17] cd apps/api && uv run ruff check . → All checks passed!
[5/17] cd apps/api && uv run ruff format --check . → 268 files already formatted
[6/17] alembic upgrade head → ok
[7/17] alembic check → No new upgrade operations detected.
[8/17] export_openapi.py --check → openapi.json is up to date
[9/17] extract_api_index.py --check → API index is up to date
[10/17] pnpm -C apps/web lint → exit 0
[11/17] pnpm -C apps/web typecheck → exit 0
[12/17] pnpm -C apps/web check:api → src/api/schema.d.ts 无 diff
[13/17] python3 scripts/check_web_style_guards.py
check_web_style_guards: ok (21 css file(s) under /root/better resume/apps/web/src)
[14/17] ... pytest ... 94 passed, 2 warnings in 7.26s
[15/17] for f in scripts/*.sh; do bash -n "$f" || exit 1; done; echo "shell syntax ok" → shell syntax ok
[16/17] check_scripts.py → script syntax ok (24 python scripts, SyntaxWarning treated as an error)
[17/17] verify_audit_evidence.py --structural → structure ok: 10 units / 122 issues / 341 citations
ALL PASS (17 commands) -- evidence: var/evidence/20261012T063529Z-all
VERIFY_ALL_EXIT=0
（[1/17] API 全量 pytest：990 passed；[2/17] coverage floors ok；TOTAL 95%）
~~~

数字：17 条命令全过，末行 ALL PASS，退出码 0；API 990 passed；coverage floors ok（deep-module 各项达下限）；web 183 passed；守卫绿。

### 3.6 前端（从仓库根跑）

~~~text
$ pnpm -C apps/web test --run
 Test Files  25 passed (25)
      Tests  183 passed (183)
$ pnpm -C apps/web typecheck
TYPECHECK_EXIT=0
$ pnpm -C apps/web lint
LINT_EXIT=0
~~~

数字：25 文件 / 183 例全绿；typecheck 与 lint 退出码 0。README §1.2 记 172 例，实测 183（≥172）；本票未改动任何前端逻辑或测试，见 §四、§五偏差 5。

### 3.7 变异证明（守卫真的钉住实现）

~~~text
$ sha_before=0b1218ff731973ad8d7a3ac1de47f572f1ae99c28a03c5b9626d018b2e9fb0cc
$ bash scripts/verify_mutation.sh --test "cd apps/api && uv run pytest tests/test_web_style_guards.py -q" \
    --file "/root/better resume/apps/web/src/pages/chat/MessageBubble.module.css" \
    --find "@media (prefers-reduced-motion: reduce) {
  .cursor {
    animation: none;
  }
}" --replace ""
== 1/3 baseline: the test must PASS on the untouched implementation ==
........  (8 passed)
== 2/3 mutate: apply --find/--replace to .../MessageBubble.module.css ==
mutated 1 occurrence in .../MessageBubble.module.css
== 2/3 red: the test must FAIL on the mutated implementation ==
.....F..
FAILED tests/test_web_style_guards.py::test_the_real_web_tree_passes_every_guard
  pages/chat/MessageBubble.module.css:51: G4 .cursor 的动画没有 prefers-reduced-motion 处理（守卫④）
ok: mutation was caught
== 3/3 restore: the test must PASS again ==
restored: .../MessageBubble.module.css sha256=0b1218ff731973ad…
PASS: baseline green -> mutation red -> restored green (.../MessageBubble.module.css)
MUT_EXIT=0 sha_after=0b1218ff731973ad8d7a3ac1de47f572f1ae99c28a03c5b9626d018b2e9fb0cc
CMP_OK restored byte-identical
~~~

数字：基线绿（8 passed）→ 变异红（1 failed，G4 点名文件行）→ 恢复绿（8 passed）；恢复后 sha256 与变异前一致，cmp 逐字节相同；--file 用绝对路径。

### 3.8 白名单读数

~~~text
$ grep -rn "allow:" apps/web/src | wc -l
44
~~~

逐条（文件:行号 — 理由，均为违规行上一行）：

~~~text
apps/web/src/styles/base.css:19:  /* allow: 键盘焦点外框线宽（2px 几何） */
apps/web/src/styles/base.css:21:  /* allow: 焦点外框与控件的偏移（2px 几何） */
apps/web/src/components/Button.module.css:6:  /* allow: 按钮发丝边框线宽（1px 几何，token 集无边框宽尺寸） */
apps/web/src/components/Collapsible.module.css:2:  /* allow: 折叠面板发丝边框线宽（1px 几何，token 集无边框宽尺寸） */
apps/web/src/components/Collapsible.module.css:31:  /* allow: 折叠箭头三角形的边长（8px 几何） */
apps/web/src/components/Collapsible.module.css:33:  /* allow: 折叠箭头三角形的边长（8px 几何） */
apps/web/src/components/Collapsible.module.css:35:  /* allow: 折叠箭头两条边的线宽（1.5px 几何） */
apps/web/src/components/Collapsible.module.css:37:  /* allow: 折叠箭头两条边的线宽（1.5px 几何） */
apps/web/src/components/Spinner.module.css:7:  /* allow: 加载点直径（12px 环径几何） */
apps/web/src/components/Spinner.module.css:9:  /* allow: 加载点直径（12px 环径几何） */
apps/web/src/components/Spinner.module.css:11:  /* allow: 加载环线宽（2px 几何） */
apps/web/src/components/Card.module.css:3:  /* allow: 卡片发丝边框线宽（1px 几何，token 集无边框宽尺寸） */
apps/web/src/components/Textarea.module.css:5:  /* allow: 输入区发丝边框线宽（1px 几何，token 集无边框宽尺寸） */
apps/web/src/components/Empty.module.css:7:  /* allow: 空态占位框发丝虚线线宽（1px 几何） */
apps/web/src/pages/interview/ResumePreviewCard.module.css:38:  /* allow: 题号列最小宽度（24px 列表几何） */
apps/web/src/pages/interview/ResumePreviewCard.module.css:73:  /* allow: 降级提示左侧警示条宽度（3px 几何） */
apps/web/src/pages/interview/RadarChart.module.css:7:  /* allow: 雷达图画布最大宽度（260px 画布尺寸） */
apps/web/src/pages/interview/RadarChart.module.css:35:  /* allow: 雷达图轴标签字号（9px，随画布缩放） */
apps/web/src/pages/interview/RoomParts.module.css:8:  /* allow: 题号列最小宽度（32px 列表几何） */
apps/web/src/pages/interview/RoomParts.module.css:67:  /* allow: 作答区顶部分隔线线宽（1px 几何） */
apps/web/src/pages/interview/RoomParts.module.css:85:  /* allow: 进度条高度（6px 几何） */
apps/web/src/pages/interview/RoomParts.module.css:87:  /* allow: 进度条最小宽度（40px 几何） */
apps/web/src/pages/chat/Composer.module.css:6:  /* allow: 输入区顶部分隔线线宽（1px 几何） */
apps/web/src/pages/chat/SessionSidebar.module.css:5:  /* allow: 会话侧栏固定宽度（260px 版式几何） */
apps/web/src/pages/chat/SessionSidebar.module.css:8:  /* allow: 侧栏右分隔线线宽（1px 几何） */
apps/web/src/pages/chat/SessionSidebar.module.css:47:  /* allow: 会话项发丝边框线宽（1px 几何，选中态复用） */
apps/web/src/pages/chat/MessageBubble.module.css:5:  /* allow: 消息气泡最大宽度（720px 版式几何） */
apps/web/src/pages/chat/MessageBubble.module.css:8:  /* allow: 气泡发丝边框线宽（1px 几何，token 集无边框宽尺寸） */
apps/web/src/pages/chat/MessageBubble.module.css:53:  /* allow: 流式光标块固定宽度（8px 几何） */
apps/web/src/pages/chat/MessageBubble.module.css:56:  /* allow: 光标块与文字的固定间距（2px 几何） */
apps/web/src/pages/InterviewIntroPage.module.css:49:  /* allow: 上传拖拽区最小高度（96px 组件几何） */
apps/web/src/pages/InterviewIntroPage.module.css:52:  /* allow: 拖拽区发丝虚线线宽（1px 几何） */
apps/web/src/pages/InterviewIntroPage.module.css:61:  /* allow: 隐藏文件输入的可访问性兜底尺寸（1px 几何） */
apps/web/src/pages/InterviewIntroPage.module.css:63:  /* allow: 隐藏文件输入的可访问性兜底尺寸（1px 几何） */
apps/web/src/pages/InterviewIntroPage.module.css:75:  /* allow: 进度条轨道高度（6px 几何） */
apps/web/src/pages/ChatPage.module.css:19:  /* allow: 页头底部分隔线线宽（1px 几何） */
apps/web/src/pages/AiSettingsPage.module.css:6:  /* allow: 设置页内容区最大宽度（960px 版式几何） */
apps/web/src/pages/AiSettingsPage.module.css:38:  /* allow: 表格行底分隔线线宽（1px 几何） */
apps/web/src/pages/InterviewRoomPage.module.css:14:  /* allow: 页头底部分隔线线宽（1px 几何） */
apps/web/src/pages/InterviewRoomPage.module.css:63:  /* allow: 提示条底部分隔线线宽（1px 几何） */
apps/web/src/pages/InterviewReportPage.module.css:42:  /* allow: 综合分英雄数字的一次性展示字号（超出 --br-text-* 字阶，非间距/常规字阶） */
apps/web/src/pages/InterviewReportPage.module.css:81:  /* allow: 逐题回放卡发丝边框线宽（1px 几何） */
apps/web/src/pages/InterviewReportPage.module.css:150:  /* allow: 维度名称列最小宽度（48px 表格列几何） */
apps/web/src/pages/InterviewReportPage.module.css:160:  /* allow: 维度分数列最小宽度（72px 表格列几何） */
~~~

### 3.9 改动面自查

~~~text
$ git diff --numstat
1	0	apps/web/src/components/Button.module.css
1	0	apps/web/src/components/Card.module.css
5	0	apps/web/src/components/Collapsible.module.css
1	0	apps/web/src/components/Empty.module.css
3	0	apps/web/src/components/Spinner.module.css
1	0	apps/web/src/components/Textarea.module.css
18	16	apps/web/src/pages/AiSettingsPage.module.css
1	0	apps/web/src/pages/ChatPage.module.css
5	0	apps/web/src/pages/InterviewIntroPage.module.css
5	1	apps/web/src/pages/InterviewReportPage.module.css
3	1	apps/web/src/pages/InterviewRoomPage.module.css
1	0	apps/web/src/pages/chat/Composer.module.css
10	0	apps/web/src/pages/chat/MessageBubble.module.css
3	0	apps/web/src/pages/chat/SessionSidebar.module.css
2	0	apps/web/src/pages/interview/RadarChart.module.css
4	2	apps/web/src/pages/interview/ResumePreviewCard.module.css
5	1	apps/web/src/pages/interview/RoomParts.module.css
2	0	apps/web/src/styles/base.css
7	0	apps/web/src/styles/tokens.css
2	1	scripts/verify.sh

$ git status --porcelain
 M apps/web/src/components/Button.module.css
 M apps/web/src/components/Card.module.css
 M apps/web/src/components/Collapsible.module.css
 M apps/web/src/components/Empty.module.css
 M apps/web/src/components/Spinner.module.css
 M apps/web/src/components/Textarea.module.css
 M apps/web/src/pages/AiSettingsPage.module.css
 M apps/web/src/pages/ChatPage.module.css
 M apps/web/src/pages/InterviewIntroPage.module.css
 M apps/web/src/pages/InterviewReportPage.module.css
 M apps/web/src/pages/InterviewRoomPage.module.css
 M apps/web/src/pages/chat/Composer.module.css
 M apps/web/src/pages/chat/MessageBubble.module.css
 M apps/web/src/pages/chat/SessionSidebar.module.css
 M apps/web/src/pages/interview/RadarChart.module.css
 M apps/web/src/pages/interview/ResumePreviewCard.module.css
 M apps/web/src/pages/interview/RoomParts.module.css
 M apps/web/src/styles/base.css
 M apps/web/src/styles/tokens.css
 M scripts/verify.sh
?? apps/api/tests/test_web_style_guards.py
?? scripts/check_web_style_guards.py
~~~

逐文件说明：

- apps/web/src/styles/tokens.css：补 --br-color-warning / --br-color-warning-bg（深浅两套）与 --br-shadow-sm / --br-shadow-md 的深色定义（守卫① / G1b）。
- apps/web/src/components/*.module.css（Button / Card / Collapsible / Empty / Spinner / Textarea）：组件几何裸值加 allow 注释（守卫②）。
- apps/web/src/styles/base.css：焦点外框几何裸值加 allow 注释（守卫②）。
- apps/web/src/pages/ChatPage / InterviewIntroPage / InterviewReportPage / InterviewRoomPage / chat/Composer / chat/MessageBubble / chat/SessionSidebar / interview/RadarChart / interview/ResumePreviewCard / interview/RoomParts .module.css：页面样式裸值按 §2.4 映射到 token 或加几何 allow（守卫②）；MessageBubble 另补 reduced-motion 覆盖（守卫④）；InterviewRoomPage 与 ResumePreviewCard 的 warning 假变量换真 token（守卫①）。
- apps/web/src/pages/AiSettingsPage.module.css：三个假变量换真 token，其余裸值走 token 或几何 allow（守卫① + ②）。
- scripts/verify.sh：add_web_contract 增守卫命令；build_scripts 的 pytest 清单增守卫测试；两处各 1 行。
- scripts/check_web_style_guards.py：守卫脚本本体（按票面规则形状实现三条守卫；未改口径），仍为未跟踪新文件。
- apps/api/tests/test_web_style_guards.py：守卫 CLI 测试 8 例（含三类坏输入各报错、allow 上一行放行、allow 同行尾注不放行），仍为未跟踪新文件。
- docs/tickets/p14-web-redesign/T1-EVIDENCE.md：本验收包（新建）。

## 四、未验证项诚实清单

- 浏览器视觉与交互：新 warning 主色/背景在浅色与深色的观感、新增深色 shadow 的观感、hover/active/focus 手感、动画节奏——AI 无浏览器与截图能力，需人工验收。
- prefers-reduced-motion 的真实生效与焦点顺序未做人工可访问性核验。
- 守卫③（断点存在性）与守卫⑤（原生控件禁用）本票不做（属 T3）；当前闸门只覆盖①②④。
- 无视觉快照测试（本阶段明确不引）。
- 42px 英雄字号、6px→4px / 2px→4px 等近似映射的逐页视觉结果未比对。
- 未跑 bash scripts/compose_smoke.sh（README §4.3 列作回归底线）；本票未改部署面与构建产物，未验证缓存头与新 bundle hash。
- 前端 183 例与文档 172 例的差异来源未在本票追溯（本票未增删前端测试）。

## 五、与提案的偏差

1. tokens.css 在 warning 之外补了 --br-shadow-sm / --br-shadow-md 的深色定义，而写入路径字面只允许加 warning。原因是守卫①的深浅双定义与「守卫退 0」的验收要求；未改浅色值、未动其他 token。请用户确认这一解释。
2. InterviewReportPage.module.css 综合分 42px 用 allow 放行，未映射到 --br-text-*（最大 26px）；硬映射会改报告页 hero 层次，待页面批裁定。
3. 无 token 对应的 6px 与 2px 间距映射到 --br-space-1（4px），属派活交接包口径「近似映射允许」（已经用户确认）；如不接受请指定目标 token 或允许几何注释。
4. 守卫测试 8 例（票面要求 ≥7）；第 8 例 test_a_same_line_allow_comment_does_not_release 钉「同行尾注不算放行」。
5. 前端实测 183 例（README/AGENTS 记 172），本票未增删任何前端测试，数字以实测为准。
6. scripts/check_web_style_guards.py 与 apps/api/tests/test_web_style_guards.py 沿用工作区既有实现与既有 7 例测试，本票未改守卫规则口径，仅补 1 例测试并格式化测试文件。
