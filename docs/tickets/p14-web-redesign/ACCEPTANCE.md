# P14 阶段验收包 — 前端视觉与版式改版

- 范围：P14 全阶段——基建批 T1–T3、视觉批 T10、页面批 T4–T8；本文件由 T9 汇总（T9 只写文档，不改代码）。
- 状态一句话：**命令面全绿**（`bash scripts/verify.sh --layer all` 17 条命令 ALL PASS）；**截图面未完成**（20 个机位全部「待拍」，是否实拍由用户三选一裁定：暂缓 / 手拍 / 主代理驱动浏览器）；**人工渲染面未执行**（手测项已入 `docs/MANUAL-TESTING.md` §1.6，等待有人在浏览器上点一遍）。
- 口径：第二节每个数字都是本轮（2026-10-12）在工作区 HEAD=`1047bd1` 上**实测重跑**的结果，完整原始日志 `/tmp/p14-t9-verify-all.log`，收口证据目录 `var/evidence/20261012T124859Z-all`。各票 EVIDENCE 的旧读数只作对照，出处逐条标注。

## 一、环境与口径

```bash
export PATH="$HOME/.local/bin:$PATH"
export UV_CACHE_DIR='/root/better resume/.cache/uv'
export BR_DATABASE_URL='postgresql+asyncpg://better_resume:better_resume@127.0.0.1:5433/better_resume'
export BR_REDIS_URL='redis://127.0.0.1:6379/0'
```

- 前端命令全部从仓库根跑；后端命令在 `apps/api` 下跑。
- `--layer all` = unit + coverage + contract + scripts，共 **17 条命令**（`bash scripts/verify.sh --list`）。
- 本票不改代码 / 测试 / 既有票与 EVIDENCE；只写 `docs/MANUAL-TESTING.md`（新增 §1.6）、`docs/design/**`、`docs/tickets/p14-web-redesign/ACCEPTANCE.md`。

## 二、可复跑命令 + 原始输出 + 数字

| # | 命令（仓库根） | 期望 | 本轮实测 | 结论 |
| --- | --- | --- | --- | --- |
| 1 | `python3 scripts/check_web_style_guards.py` | exit 0，末行 ok | exit 0；`check_web_style_guards: ok (27 css file(s) under /root/better resume/apps/web/src)` | ✅ |
| 2 | `grep -rn 'allow:' apps/web/src \| wc -l` | 41 | 41 | ✅ |
| 3 | `pnpm -C apps/web test --run` | ≥172 例只增不减 | 26 文件 / 202 例全绿 | ✅ |
| 4 | `pnpm -C apps/web lint` | exit 0 | exit 0 | ✅ |
| 5 | `pnpm -C apps/web typecheck` | exit 0 | exit 0 | ✅ |
| 6 | `bash scripts/verify.sh --layer all` | 17 命令，末行 ALL PASS | 17 命令全过；`ALL PASS (17 commands) -- evidence: var/evidence/20261012T124859Z-all`；exit 0 | ✅ |
| 7 | 上表 6 内的 `[1/17]`（API 全量 pytest + coverage） | 绿 | `997 passed, 3 warnings in 83.64s`；`TOTAL 6553 305 95%` | ✅ |
| 8 | 上表 6 内的 `[2/17]` coverage floors | ok | `floors ok` | ✅ |
| 9 | 上表 6 内的 `[17/17]` 审计结构级 | ok | `structure ok: 10 units / 122 issues / 341 citations` | ✅ |
| 10 | `cd apps/api && uv run pytest tests/test_web_style_guards.py --junitxml=/tmp/p14-guards.xml` | 守卫用例全绿 | `<testsuite ... errors="0" failures="0" skipped="0" tests="15"` | ✅ |
| 11 | `cd apps/api && uv run pytest tests/test_verify_script.py --junitxml=/tmp/p14-verifypin.xml` | 层图钉全绿 | `<testsuite ... errors="0" failures="0" skipped="0" tests="27"` | ✅ |

### 2.1 原始输出摘录

守卫与白名单（本轮实测）：

```text
$ python3 scripts/check_web_style_guards.py
check_web_style_guards: ok (27 css file(s) under /root/better resume/apps/web/src)
guard_exit=0
$ grep -rn 'allow:' apps/web/src | wc -l
41
```

前端全量（本轮实测，从仓库根）：

```text
$ pnpm -C apps/web test --run
 Test Files  26 passed (26)
      Tests  202 passed (202)
   Start at  20:52:23
$ pnpm -C apps/web lint    → lint_exit=0
$ pnpm -C apps/web typecheck → typecheck_exit=0
```

`--layer all` 关键行（本轮实测）：

```text
[1/17] cd apps/api && uv run pytest --cov=better_resume ...
TOTAL                                                      6553    305    95%
997 passed, 3 warnings in 83.64s (0:01:23)
[2/17] cd apps/api && uv run python scripts/check_coverage_floors.py --json coverage-api.json
floors ok
[3/17] pnpm -C apps/web exec vitest run
 Test Files  26 passed (26)
      Tests  202 passed (202)
[4/17] cd apps/api && uv run ruff check .  → All checks passed!
[10/17] pnpm -C apps/web lint
[11/17] pnpm -C apps/web typecheck
[13/17] python3 scripts/check_web_style_guards.py
check_web_style_guards: ok (27 css file(s) under /root/better resume/apps/web/src)
[17/17] ... verify_audit_evidence.py --structural
structure ok: 10 units / 122 issues / 341 citations
ALL PASS (17 commands) -- evidence: var/evidence/20261012T124859Z-all
```

红线区核对（`docs/MANUAL-TESTING.md` §1.1–1.4 一字未动）：

```text
$ git show HEAD:docs/MANUAL-TESTING.md | sed -n '/^### 1\.1 /,/^## 1\.5 /p' | head -n -1 > /tmp/p14-red-head.txt
$ sed -n '/^### 1\.1 /,/^## 1\.5 /p' docs/MANUAL-TESTING.md | head -n -1 > /tmp/p14-red-work.txt
$ sha256sum /tmp/p14-red-head.txt /tmp/p14-red-work.txt
42b206581016305ce0332c2ff2b9413326ba582f5fb938fa11644a124e466d3c  /tmp/p14-red-head.txt
42b206581016305ce0332c2ff2b9413326ba582f5fb938fa11644a124e466d3c  /tmp/p14-red-work.txt
$ diff /tmp/p14-red-head.txt /tmp/p14-red-work.txt; echo "region_diff_exit=$?"
region_diff_exit=0
$ git diff -U0 docs/MANUAL-TESTING.md | grep '^@@'
@@ -59,0 +60,38 @@
```

说明：两份 §1.1–1.4 文本 sha256 相同、`diff` 退出 0；整文件 diff 只有一个新增 hunk（新 §1.6，插在 §1.5 之后、§2 之前，行号 60 起），未触碰红线区。

## 三、分票关键读数与结论

### 3.1 基建批 T1–T3

| 票 | 关键读数 | 出处 |
| --- | --- | --- |
| T1 守卫闸门①②④ + 存量违规清零 | 三条守卫进 verify 的 web 契约层；守卫用例本轮重跑 15 例（errors=0 / failures=0 / skipped=0）；verify 层图钉本轮重跑 27 例全绿；存量裸值与假变量清零 | 本轮实测 + `T1-EVIDENCE.md` §三 |
| T2 视觉 token 扩充 | 靛蓝色阶 + 3 个渐变 + 3 级阴影 + `--br-radius-xs` / `--br-space-7` 等新 token；既有 37 个 token 零改名零删除；本票 allow 维持 48 条、新增 0 | `T2-EVIDENCE.md` §三.3–3.5 |
| T3 页壳 + 两档响应式 + 样式化组件 + 守卫③⑤ | AppShell 顶栏 + 居中内容容器；断点档 1024；Select / Input / Table / Badge / Skeleton 落地；守卫③⑤先红后绿；新增 3 例行为单测 | `T3-EVIDENCE.md` §三、§五 |

### 3.2 视觉批 T10

| 项 | 关键读数 | 出处 |
| --- | --- | --- |
| hero 字阶 | `--br-text-hero: 42px`，唯一消费点报告页综合分；allow 48 → 47 | `T10-EVIDENCE.md` §二.3、§3.1 |
| 交互态补课 | Button / Input / Select / 顶栏导航 / 会话项与删除键 / 可点行补 hover / active / focus-visible；新增或改写的 9 处 transition 全为 `--br-duration-fast`（120ms）且同文件同选择器有 reduced-motion 重访 | `T10-EVIDENCE.md` §3.3、§3.4 |
| 预留 token 落消费点 | `--br-color-accent-hover` / `--br-color-accent-active` / `--br-color-accent-muted` / `--br-radius-xs` 各有 ≥1 处消费 | `T10-EVIDENCE.md` §3.2 |

### 3.3 页面批 T4–T8

| 票 | 页面（路由） | 关键读数 | 出处 |
| --- | --- | --- | --- |
| T4 | 报告页 `/interview/report/:sessionId` | hero（综合分 + 雷达生长动画 + 四维小分条）+ 按类卡片栅格 + 逐题折叠分组；`InterviewReportPage.test.tsx` 由 7 例增到 11 例（净增 4）；雷达几何与 11 例测试零改动 | `T4-EVIDENCE.md` §三.4 |
| T5 | 上传页 `/interview` | 主区 7fr:5fr；dropzone 放大为主视觉（最小高度 96 → 220，同文件 allow 条数不变）；侧重 Select 每项带说明；进度条带百分比与阶段文案；继续列表卡片行；`InterviewIntroPage.test.tsx` 9 → 12 例 | `T5-EVIDENCE.md` §三.2–3.3 |
| T6 | 面试间 `/interview/room/:sessionId` | 二级行步骤条「题 X / Y」+ 类别徽章；考察要点标签化；最新反馈高亮；composer 卡片化（字数计数 / 录音态 / 快捷键提示）；<1024 堆叠 + 反馈折叠 + composer 吸底；`InterviewRoomPage.test.tsx` 9 → 12 例；转写合并与语音 6 文件 49 例绿 | `T6-EVIDENCE.md` §三.2–3.3 |
| T7 | 聊天页 `/chat` | 并入页壳顶栏；会话侧栏二级化（选中态渐变边）；消息气泡与 composer 复用同一卡片配方；零散旧 h2 移除；新增 5 例；转写 / SSE 面 11 文件 77 例绿；allow 43 → 41 | `T7-EVIDENCE.md` §三.3–3.5 |
| T8 | 设置页 `/settings/ai` | token 重修（删本页唯一 960px 页宽 allow）；表格样式化（表头弱化 / 行 hover / 状态徽章）；保存反馈「保存中 / 已保存」；`AiSettingsPage.test.tsx` 8 → 9 例；本页 allow 1 → 0 | `T8-EVIDENCE.md` §三.2–3.3 |

### 3.4 本轮聚合实测（我的重跑，覆盖上面各票的树级读数）

- 前端 `pnpm -C apps/web test --run`：**26 文件 / 202 例全绿**（README §1.2 记 172，只增不减）。
- 后端全量 pytest：**997 passed**，coverage **TOTAL 6553 行 / 未覆盖 305 / 95%**，coverage floors **ok**。
- `bash scripts/verify.sh --layer all`：**17 条命令全过，末行 `ALL PASS (17 commands)`，exit 0**，证据目录 `var/evidence/20261012T124859Z-all`。

## 四、未验证项（诚实清单）

以下均为**未验证**，不是通过项：

1. **截图段未完成**：20 个机位全部「待拍」，本轮无任何截图入库（见 §六与 `docs/design/SHOT-LIST.md`）；是否实拍的三选一裁定未定。
2. **人工渲染半边未执行**：`docs/MANUAL-TESTING.md` §1.6 的 14–41 项全部未跑；hover / active / focus 手感、深浅色观感、reduced-motion 观感均无人工核验。
3. **两档断点的真机行为未核**：jsdom 不应用媒体查询，<1024 塌缩、侧栏折叠、composer 吸底只有静态声明与单测（各票 §四）。
4. **`bash scripts/compose_smoke.sh` 未跑**（README §4.3 回归底线之一；各票 §四均登记）；本阶段未改部署面，缓存头与新 bundle hash 未核。
5. **`bash scripts/verify.sh --layer real` 与 `--layer e2e` 未跑**（`--layer all` 不含这两层）；真模型链路与黄金路径端到端仍按各自票据的状态。
6. **登录门（README §1.4 七块之一）无承接实现票**：T4–T8 / T10 的工作区改动里没有 `LoginGate.tsx` / `LoginGate.module.css`（`git status --porcelain` 无该文件，CSS 仍是最初的居中单卡，无渐变 / hero）；T3 票的「不做」写明登录门 hero 化不在其内。**该块是否另立票或本阶段降级，停下来等用户裁定。**
7. **等价性守卫不算新红-绿切片**：T6 / T7 各有「实现前即绿」的等价性用例（T6 §五.3、T7 §五.4 已自行登记）。
8. **未做视觉快照测试**（本阶段明确不引）。

## 五、与提案的偏差汇总（逐条引用各 EVIDENCE §五 原文）

下表逐条引用各票 `*-EVIDENCE.md` §五的原文——**不改写、不重排、不合并成新规则**；多行条目以 `<br>` 保留原顺序。共 **60 条**。

### T1（基建批，共 6 条）

出处：`docs/tickets/p14-web-redesign/T1-EVIDENCE.md` §五

| # | 原文 |
| --- | --- |
| 1 | tokens.css 在 warning 之外补了 --br-shadow-sm / --br-shadow-md 的深色定义，而写入路径字面只允许加 warning。原因是守卫①的深浅双定义与「守卫退 0」的验收要求；未改浅色值、未动其他 token。请用户确认这一解释。 |
| 2 | InterviewReportPage.module.css 综合分 42px 用 allow 放行，未映射到 --br-text-*（最大 26px）；硬映射会改报告页 hero 层次，待页面批裁定。 |
| 3 | 无 token 对应的 6px 与 2px 间距映射到 --br-space-1（4px），属派活交接包口径「近似映射允许」（已经用户确认）；如不接受请指定目标 token 或允许几何注释。 |
| 4 | 守卫测试 15 例（票面要求 ≥7）；含 test_a_same_line_allow_comment_does_not_release 钉「同行尾注不算放行」。 |
| 5 | 前端实测 186 例（README/AGENTS 记 172），本票未增删任何前端测试，数字以实测为准。 |
| 6 | scripts/check_web_style_guards.py 与 apps/api/tests/test_web_style_guards.py 沿用既有实现与既有测试，守卫规则口径未变。 |

### T2（基建批，共 5 条）

出处：`docs/tickets/p14-web-redesign/T2-EVIDENCE.md` §五

| # | 原文 |
| --- | --- |
| 1 | 阴影命名保留 --br-shadow-sm（卡片）/ --br-shadow-md（浮层）为主名，新增 --br-shadow-sticky 覆盖吸底；未改成 --br-shadow-card / --br-shadow-overlay。理由是票面拍死「以保留现有语义名为主名」。若页面批更倾向角色名，请在 T3/T4 指定后统一改名。 |
| 2 | --br-radius-xs（2px）与 --br-space-7（40px）的具体取值由执行方按现有步长最小补档选定，票据只写「圆角微调 / 间距补档」未给档位与数值；请确认这两个取值。 |
| 3 | 字阶未新增、未改值：票面禁改字号语义档位，且字号牵动页面版式（T4–T8）；「字阶微调」在本票落成「维持现有五档」，如需 hero 大字号请在 T4 与 T1 遗留的 42px allow 一并裁定。 |
| 4 | 本票未改任何 module.css，也未新增任何 allow（白名单 48 条）；「消费点迁移」体现为 --br-color-accent 的集中值迁移，而非逐文件替换。 |
| 5 | 9 个新 token 全部无本票消费点，按「预留槽位」登记，预计消费票见 §3.5；若要求在 T2 内接入消费点，需要把 T3 的组件样式提前，超出本票「不做组件样式」的边界。 |

### T3（基建批，共 10 条）

出处：`docs/tickets/p14-web-redesign/T3-EVIDENCE.md` §五

| # | 原文 |
| --- | --- |
| 1 | **断言调整清单（唯一一条）**：apps/web/src/App.test.tsx 第 23 行由 getByText("还没有消息") 改为 findByText("还没有消息")。原因：页壳把 heading「better-resume」移进顶栏后，findByRole("heading") 在 ChatPage 仍显示「正在检查登录状态…」时就满足，紧随其后的同步 getByText 会在空态渲染前执行。改法是等待同一文本，测试意图（已登录访客看到聊天壳与空态）不变，属票面允许的「文本 / 角色位置」类调整；未删除或削弱任何断言。 |
| 2 | 写入路径扩到 apps/web/src/App.test.tsx（票面唯一写入路径未列该文件）。除此之外未扩路径：scripts/verify.sh 零改动；apps/web/src/api、audio、stream 与 openapi.json / schema.d.ts 零改动。 |
| 3 | 断点实现取「窄屏单列为默认、@media (min-width: 1024px) 恢复双栏」的写法（票面表述为 ≥1024 照旧）；媒体查询值仍是 1024px，并满足验收项「加 ≥1 条 (min-width: 1024px) 档断点」。 |
| 4 | 二级栏「顶部折叠」用原生 <details> / <summary>（窄屏默认收起），未引入 JS 开关与对应行为单测；票面行为单测只点名导航高亮与 Skeleton，本项没有指定测试缝。 |
| 5 | 页内标题由 h1 降为 h2（顶栏品牌成为唯一 h1）。既有页面测试未断言这些标题，断言零改动；此为角色位置调整。 |
| 6 | 删除 InterviewIntroPage.module.css 的 .back 与 AiSettingsPage.module.css 的 .table 规则：返回对话链接与裸 table 一并消失，规则失去消费点，避免死代码。 |
| 7 | Badge 未消费 --br-gradient-badge，五档 tone 全走语义色 token；渐变 token 的消费留给 T4–T8（T2 已登记为预留槽位）。 |
| 8 | 新增 3 例行为单测（AppShell 导航高亮 2 + Skeleton 1）超出票面最小集（导航高亮，Skeleton 仅在带逻辑时测）；未改数据层断言、未删测试。 |
| 9 | styles/tokens.css 新增 --br-width-content: 1200px（写入路径 #4 允许的内容容器宽度 token 最小新增）；为非主题依赖，无需 prefers-color-scheme: dark 重述，G1/G1b 通过。 |
| 10 | SessionSidebar.tsx 内联 class 拼接由模板字符串改为数组 join、aria-label 由模板字符串改为字符串拼接（等价），以避免外层工具链对模板字符串的处理差异；渲染结果与可访问名不变。 |

### T10（视觉批，共 6 条）

出处：`docs/tickets/p14-web-redesign/T10-EVIDENCE.md` §五

| # | 原文 |
| --- | --- |
| 1 | 除 Badge 组件外，同类小徽记（`RoomParts.module.css` 与 `InterviewReportPage.module.css` 的 `.badge`）也改用 `--br-radius-xs`，以保证同类徽记圆角一致；未扩到卡片 / 按钮 / 输入控件。 |
| 2 | Input / Select 的 focus 强化采用「border-color accent + 4px accent-muted 光晕」，在全局 `:focus-visible` 外框之外叠加，未替换、未削弱全局环（base.css 零改动）。 |
| 3 | ghost 的 `:active` 以 `--br-color-border` 作按下底色（既有 border 系 token）；本批要求「secondary/ghost 用 surface/text-muted 系」，此处用 border 系作按下反馈，取「既有 token 内的最近中性档」，未引入新色值。 |
| 4 | 上传页「继续上次面试」行 hover 用 `--br-color-accent-muted` 弱背景而非 surface 系，理由是行位于 surface 底色的 Card 内、surface 系看不出变化；该 token 的用途限定为 hover / 选中弱背景，符合本批口径。 |
| 5 | 未新增任何 allow；白名单由 48 降到 47，唯一删项即本票要清理的综合分 42px。 |
| 6 | 新增 transition 全部取 `--br-duration-fast`（120ms），未使用 `--br-duration-normal`；本批要求二者皆可，取更短的一档以贴合「状态反馈」而非「进场」。 |

### T4（页面批，共 6 条）

出处：`docs/tickets/p14-web-redesign/T4-EVIDENCE.md` §五

| # | 原文 |
| --- | --- |
| 1 | 报告页第二行「按类给分」用既有 Card 组件承载每类卡片（而非页面自定义卡片容器），以复用卡片的 1px 发丝边框与圆角，同时不新增 allow。 |
| 2 | 四维小分条每行文案取「分值 + 维度名」（分值在前），而非「维度名 + 分值」：既有测试以 getByText(/^维度名/) 断言雷达轴标签唯一出现，分值前置可让雷达与小分条同时保留各自的维度文字而该断言继续通过（既有断言一字未改）。若用户更接受「维度名 + 分值」，需要同步调整那条既有断言的作用域，超出本票「不改既有测试断言」的红线，故停下来报。 |
| 3 | 无分数类别改用既有 Badge 组件（tone=neutral）承载「样本不足」，因此该分支不再有「<类别>得分」的 aria-label；判定与文案语义未变（P11）。有分数类别的数字位 aria-label 原样保留。 |
| 4 | hero 未铺渐变底，--br-gradient-hero 只落在卡顶部一条 40×4 徽条上，取 README §1.5「渐变只做点缀，不铺大面」。 |
| 5 | 「全部展开/收起」在只有 1 个分组时不渲染（单组时该开关无意义）；该渲染条件由线框未写明处按保守做法选定。 |
| 6 | 本票未改 RadarChart.tsx（生长动画只挂在既有 .area / .dot 类上），几何与 11 例测试零改动。 |

### T5（页面批，共 6 条）

出处：`docs/tickets/p14-web-redesign/T5-EVIDENCE.md` §五

| # | 原文 |
| --- | --- |
| 1 | 「每项带一行说明」落地为 option 单行文本内追加说明（原生 select 无法渲染两行 option）；未新增自定义下拉组件（票面限既有样式化组件）。说明表在本票新增于页面文件内，未改 `interviewTypes.ts`。 |
| 2 | 「hover 进入」：整行未设为按钮，进入动作由行内「继续」按钮承担，以保留既有可访问名与既有断言；行的 hover 弱背景 + 阴影由 T10 口径延伸。 |
| 3 | 新增拖拽行为与一条行为单测（票面切片只点名 3 条缝）：线框要求 dropzone 出现「拖拽文案」，若只有文案没有 drop 接线，文案失真；实现复用既有 `selectFile`，未改任何上传语义。 |
| 4 | 上传卡 `raised`、ResumePreviewCard 统计改瓦片、空态插画走 Empty 的 `action` 槽位：均为线框未写处的保守做法，登记待确认。 |
| 5 | 时间展示不做时区换算；如要本地时区展示，需要产品口径。 |
| 6 | 本票写入路径之外的并行票文件不属于本票改动面，见 §3.6；本票文件与全量套件的收口读数均为绿（§3.3）。 |

### T6（页面批，共 8 条）

出处：`docs/tickets/p14-web-redesign/T6-EVIDENCE.md` §五

| # | 原文 |
| --- | --- |
| 1 | **断言调整清单（3 条，全部在 InterviewRoomPage.test.tsx，均为表现层定位而非削弱）**：<br>- getByText("考察要点：取舍、量化") → getByRole("list", { name: "考察要点" }) + toHaveTextContent("取舍") / ("量化")（focus_points 由顿号串改为标签，线框要求）。<br>- getByText("已答 0 / 2 题") → getByText("题 1 / 2")；getByText("已答 1 / 2 题") → getByText("题 2 / 2")（线框的步骤条文案就是「题 X / Y」）。<br>- 没有删除任何断言；转写/VoiceWiring 测试零改动。 |
| 2 | **「反馈按时间分组」落为单一时间序分组**：数据里没有 per-turn 时间戳，拒绝伪造。若后续要按日期分组，需先有 turn 级时间字段（不在本票范围）。 |
| 3 | **新增 3 例行为单测**，票面点名两条缝（反馈分组/最新高亮、composer 行为等价）；其中「无待答题目时提交与输入禁用」实现前即绿，作为既有状态驱动的等价性守卫，不构成新的红-绿切片。折叠开关的开合（aria-expanded）断言并进反馈用例，未单立缝。 |
| 4 | **窄屏折叠用 Button + data-open 自实现**，未复用 Collapsible（无法在 ≥1024 只隐掉开关）、未用 <details>（闭包内容在宽屏强制展开不可靠）。这带来一个页面级 UI state（feedbackOpen），仅控制可见性，不参与提交/禁用语义。 |
| 5 | **页内 h2「模拟面试」移除**：页壳顶栏是唯一品牌位，线框二级行只列步骤条 / 类别徽章 / 结束按钮。既有测试未断言该标题。 |
| 6 | **placeholder 文案由「用具体案例回答（Ctrl/Cmd + Enter 提交）」改为「用具体案例回答」**，快捷键提示改为常显一行（线框要求「快捷键提示」，避免同一提示出现两处）。 |
| 7 | **QuestionCard 新增可选 category prop**：roomStore 的 InterviewTurn 不含 category，为避免改数据层，由页面把 state.currentQuestion.category 直接传下去；该 prop 可选，其他调用点与测试无需变更。 |
| 8 | 进度条由「宽度百分比 + 已答 X / Y 题」改为「一题一格 + 题 X / Y」，删掉了原 .progressBar 的 min-width allow 行；旧的 progressBar class 无其他引用，未留死代码。 |

### T7（页面批，共 7 条）

出处：`docs/tickets/p14-web-redesign/T7-EVIDENCE.md` §五

| # | 原文 |
| --- | --- |
| 1 | 删除页内 h2「对话」：顶栏主导航已用 aria-current 表达当前页，README §1.4 聊天页线框未列标题行；这只涉及标题展示，改动前后 ChatPage.test.tsx 均无相关断言。属解释性取舍，需用户确认。 |
| 2 | 模型选择落主区头：顶栏在 components/AppShell 内、不在写入路径，且模型是会话上下文操作；线框允许的两个落点只选了其一，未两处都放、未删功能。 |
| 3 | composer 未叠 position: sticky：聊天页 composer 已是 flex 列固定底栏，sticky 无实际作用；描边 / 圆角 / 吸底阴影 / focus-within 照面试间配方。 |
| 4 | 新增 5 例单测：3 例真红-绿（字数计数、快捷键 + 录音态、侧栏 aria-current），1 例 aria-current 的反向断言（/chat 无会话时不标）实现前即绿，1 例「空文本禁用发送」是既有行为的等价性守卫、实现前即绿。后两例是等价性守卫，不构成新的红-绿切片。 |
| 5 | 快捷键提示文案取聊天页真实按键「Enter 发送，Shift+Enter 换行」，未照抄面试间的「Ctrl / ⌘ + Enter 提交」；Enter 提交语义零改动。 |
| 6 | allow 白名单：票面口径写 43，实测 41（净 -2，未新增，明细见 §3.2）。 |
| 7 | 跨页样式重复（interview/RoomParts 与 InterviewReportPage 的 badge / composer）未在本票收敛：这两处在写入路径之外，把配方提到 components/ 属「动共享层」，按红线不做；本票只收敛 pages/chat 内的复制。 |

### T8（页面批，共 6 条）

出处：`docs/tickets/p14-web-redesign/T8-EVIDENCE.md` §五

| # | 原文 |
| --- | --- |
| 1 | 删除设置页 `.page` 的 `max-width: 960px`（含其 allow），把页宽交给 README §1.4 页壳的居中内容容器（`--br-width-content`，1200）。线框未写设置页自身宽度，本页原来是唯一一处页面级宽度上限；取「与其他页一致、清掉本页唯一裸值」的保守做法。若要求设置页单独窄排，请点名目标宽度并需要新 token 或保留 allow。 |
| 2 | 保存反馈除「已保存」提示外，还把保存按钮文案在请求进行中切为「保存中」。既有 Button 的 loading 只给禁用 + aria-busy，没有可见文案；票面写「保存中/已保存」，故文案由本页给（不新增组件能力、不改 Button）。 |
| 3 | 「已保存」提示在再次编辑任意一行时清除，且只保留最近一次成功保存的那一行；这是线框未规定的交互细节，取「提示不早于真实状态」的保守口径。 |
| 4 | 未配置徽章把凭据提示文案放进同一个 Badge 元素内（而非「徽章=未配置」+ 另一行提示），以便既有测试对文本内容的断言一字不改地继续成立。 |
| 5 | `.hint` 行高由裸 1.6 改为 `--br-leading-normal`（1.65），属 token 化的极小视觉位移。 |
| 6 | 白名单由 47 降为 46（删本页 960px 一条），未新增任何 allow。 |

## 六、截图状态

- **本轮截图：未拍 / 待拍。** 票面切片 2「截图齐套」在本轮判**未完成**，如实记。
- 机位定义已就位：`docs/design/SHOT-LIST.md` 给出 7 个页面 20 个机位（桌面 1280×800 为主、窄屏 390×844 抽测、浅色为主深色抽 1–2 张），全部标注「待拍」。
- 拍摄红线：截图里不许出现真实简历内容，一律用**合成简历**与样例会话 / 报告数据。
- **三选一裁定待定**：暂缓 / 手拍 / 主代理驱动浏览器；裁定前不入库任何图。

## 七、改动面自查

本票改动面：只写 `docs/MANUAL-TESTING.md`（+38 行，新增 §1.6）与新建的 `docs/design/README.md`、`docs/design/SHOT-LIST.md`、`docs/tickets/p14-web-redesign/ACCEPTANCE.md`。

`apps/web/**` 的 26 个改动文件来自页面批 T4–T8 与视觉批 T10，本票未触碰；T1–T8 / T10 的票面与各自 EVIDENCE（含未跟踪的 T4–T8-EVIDENCE）均未改；无 `git commit` / `git push`。

```text
$ git status --porcelain
 M apps/web/src/pages/AiSettingsPage.module.css
 M apps/web/src/pages/AiSettingsPage.test.tsx
 M apps/web/src/pages/AiSettingsPage.tsx
 M apps/web/src/pages/ChatPage.module.css
 M apps/web/src/pages/ChatPage.test.tsx
 M apps/web/src/pages/ChatPage.tsx
 M apps/web/src/pages/InterviewIntroPage.module.css
 M apps/web/src/pages/InterviewIntroPage.test.tsx
 M apps/web/src/pages/InterviewIntroPage.tsx
 M apps/web/src/pages/InterviewReportPage.module.css
 M apps/web/src/pages/InterviewReportPage.test.tsx
 M apps/web/src/pages/InterviewReportPage.tsx
 M apps/web/src/pages/InterviewRoomPage.module.css
 M apps/web/src/pages/InterviewRoomPage.test.tsx
 M apps/web/src/pages/InterviewRoomPage.tsx
 M apps/web/src/pages/chat/Composer.module.css
 M apps/web/src/pages/chat/Composer.test.tsx
 M apps/web/src/pages/chat/Composer.tsx
 M apps/web/src/pages/chat/MessageBubble.module.css
 M apps/web/src/pages/chat/MessageList.module.css
 M apps/web/src/pages/chat/MessageList.tsx
 M apps/web/src/pages/chat/SessionSidebar.tsx
 M apps/web/src/pages/interview/RadarChart.module.css
 M apps/web/src/pages/interview/ResumePreviewCard.module.css
 M apps/web/src/pages/interview/RoomParts.module.css
 M apps/web/src/pages/interview/RoomParts.tsx
 M docs/MANUAL-TESTING.md
?? docs/design/
?? docs/tickets/p14-web-redesign/ACCEPTANCE.md
?? docs/tickets/p14-web-redesign/T4-EVIDENCE.md
?? docs/tickets/p14-web-redesign/T5-EVIDENCE.md
?? docs/tickets/p14-web-redesign/T6-EVIDENCE.md
?? docs/tickets/p14-web-redesign/T7-EVIDENCE.md
?? docs/tickets/p14-web-redesign/T8-EVIDENCE.md
```

```text
$ git diff --numstat
12	8	apps/web/src/pages/AiSettingsPage.module.css
28	0	apps/web/src/pages/AiSettingsPage.test.tsx
38	25	apps/web/src/pages/AiSettingsPage.tsx
6	16	apps/web/src/pages/ChatPage.module.css
16	0	apps/web/src/pages/ChatPage.test.tsx
20	23	apps/web/src/pages/ChatPage.tsx
130	14	apps/web/src/pages/InterviewIntroPage.module.css
60	2	apps/web/src/pages/InterviewIntroPage.test.tsx
120	29	apps/web/src/pages/InterviewIntroPage.tsx
171	42	apps/web/src/pages/InterviewReportPage.module.css
108	0	apps/web/src/pages/InterviewReportPage.test.tsx
164	66	apps/web/src/pages/InterviewReportPage.tsx
69	13	apps/web/src/pages/InterviewRoomPage.module.css
84	6	apps/web/src/pages/InterviewRoomPage.test.tsx
46	17	apps/web/src/pages/InterviewRoomPage.tsx
72	6	apps/web/src/pages/chat/Composer.module.css
38	0	apps/web/src/pages/chat/Composer.test.tsx
37	22	apps/web/src/pages/chat/Composer.tsx
3	9	apps/web/src/pages/chat/MessageBubble.module.css
8	0	apps/web/src/pages/chat/MessageList.module.css
6	4	apps/web/src/pages/chat/MessageList.tsx
1	0	apps/web/src/pages/chat/SessionSidebar.tsx
25	0	apps/web/src/pages/interview/RadarChart.module.css
9	1	apps/web/src/pages/interview/ResumePreviewCard.module.css
128	19	apps/web/src/pages/interview/RoomParts.module.css
70	21	apps/web/src/pages/interview/RoomParts.tsx
38	0	docs/MANUAL-TESTING.md
```

本票自己写出的文件（`--untracked-files=all` 视角）：

```text
$ git status --porcelain --untracked-files=all docs/design docs/tickets/p14-web-redesign/ACCEPTANCE.md docs/MANUAL-TESTING.md
 M docs/MANUAL-TESTING.md
?? docs/design/README.md
?? docs/design/SHOT-LIST.md
?? docs/tickets/p14-web-redesign/ACCEPTANCE.md
```

`docs/design/` 下的 7 个页面子目录（shell / login-gate / upload / interview-room / report / chat / settings）已建，因空目录不被 git 跟踪，未出现在 `git status` 里；对应截图落盘后即为 `??` 新文件。
