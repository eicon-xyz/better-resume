# P14 提案：前端视觉与版式改版（把「太简洁」治好，不动业务）

- Status: ready-for-agent

> **依据**：前端改版 grilling 逐轮拍板（2026-10-12，Q1–Q16 全部有用户确认的推荐答案）。
> **状态**：已规格化并**经用户点头**（2026-10-12）：线框七块逐块确认、报告页雷达生长动画纳入、截图目录 `docs/design/` 确认；待 implement（按上下文卫生开新会话）。
> 决议依据：D24（样式体系不切换）、D25（改版方法论：线框先行 / 两批验收 / 双口径质量）。

## 1. 范围

### 1.1 一句话

在**不换技术栈、不动业务逻辑与 REST 契约**的前提下，把前端从「系统字体 + 蓝 accent + 1px 边框卡片」的极简手搓 SPA，
升级为「产品工具风为底、Linear 级细节质感」的精致界面：治**视觉质感**与**信息布局**两个主病灶，补**交互反馈**课，
以**线框提案**逐页确认后施工。

### 1.2 现状（已核实，带出处）

| 现状 | 依据 |
| --- | --- |
| 样式体系 = CSS Modules + 35 个自研 `--br-*` token，无 Tailwind/shadcn；只有 6 个手写原子组件（Button/Card/Collapsible/Empty/Spinner/Textarea） | `apps/web/src/styles/tokens.css:4-47`；`apps/web/src/components/index.ts`；`apps/web/package.json` 依赖清单 |
| **token 漂移**：设置页基本脱节（裸 px/hex），且有 **4 个被引用但从未定义的假变量**（`--br-text-muted` / `--br-border` / `--br-color-warning` / `--br-color-warning-bg`） | `apps/web/src/pages/AiSettingsPage.module.css`；`InterviewRoomPage.module.css:63`；`ResumePreviewCard.module.css:72-73` |
| **无页壳**：无 AppShell/顶栏/页脚，6 个页面各写各的 header（5 个 h1）；聊天页独占固定 260px 会话侧栏 | `apps/web/src/App.tsx:31-38`；各页面 `header` 标签；`SessionSidebar.module.css:5` |
| **全站 0 个宽度断点**：两列栅格与侧栏窄屏不塌缩；仅有的 @media 是深色与 reduced-motion | 全 src `@media` 仅 `tokens.css:49`、`Spinner.module.css:21` |
| **动效近乎为零**：transition×4、keyframes×2、hover 仅 1 条、active 0 条；focus 只有浏览器全局外框；无骨架屏 | `Button.module.css:11,45`；`base.css:18-21`；grep skeleton=0 |
| 页面级样式重复：badge/composer 在 RoomParts / MessageBubble / InterviewReportPage 近似重复 3 处 | `RoomParts.module.css:14-20`、`InterviewReportPage.module.css:96-102`、`Composer.module.css` |
| 工程门槛现状全绿：strict tsc、type-checked eslint、vitest 25 文件 **172 例**（纯逻辑，无快照/视觉） | `apps/web/tsconfig.json:8-12`；`eslint.config.js:11`；`pnpm -C apps/web test --run` |
| 报告雷达图为手绘 SVG（几何有 11 例测试）；空态/加载态有、骨架屏无 | `pages/interview/RadarChart.tsx`；`src/interview/radar.ts` + `radar.test.ts` |

### 1.3 本阶段要做的事

1. **基建批**：token 扩充与清漂移（假变量归零、靛蓝色阶、渐变/阴影/层级 token）＋ 页壳（顶栏 + 内容容器）＋ 两档响应式断点 ＋ 样式化组件补齐（Select / Input / Table / Badge / Skeleton）＋ **5 条守卫进 CI** ＋ 前后截图底座。
2. **页面批**（按序）：报告页 + 上传页（作品集第一眼）→ 面试间 → 聊天页 + 设置页，逐页按 §1.4 线框施工。
3. **配套**：手测清单渲染半边更新（hover/active 等人工项入册）；截图入库（兼作品集素材）。

### 1.4 线框提案（逐页「现状 vs 提案」，**待你逐页点头**）

**页壳（全局）**
- 现状：无；每页自渲染 header；聊天页独有 260px 侧栏；0 断点。
- 提案：顶栏（产品名 + 主导航「对话 / 面试 / AI 设置」+ 右上用户区与退出）+ 居中内容容器（max-width ≈ 1200）；聊天页会话侧栏保留为**页内二级栏**；页内只留标题行与上下文操作。`<1024`：两列塌单列、二级栏改顶部折叠。

**登录门（首屏）**
- 现状：居中单卡 + 单行用户名输入。
- 提案：全屏门面——低饱和靛蓝渐变背景 + 居中 hero（大字阶产品名 + 一句话价值主张）+ 玻璃质感登录卡（输入 + 进入）；纯键盘可达保留。

**上传页（面试开始）**
- 现状：1fr:1fr 左上传卡（select + dashed dropzone + 进度条 + 按钮）右预览卡；下方「继续上次面试」平铺列表。
- 提案：主区改 **7fr:5fr**（上传优先）；dropzone 放大为主视觉（图标 + 拖拽文案 + 支持格式）；面试侧重换样式化 Select（每项带一行说明）；进度条带百分比与阶段文案；「继续上次面试」改卡片行（时间 / 状态徽章 / hover 进入），空态用插画感 Empty。

**面试间**
- 现状：header 进度条 + 结束按钮；3fr:2fr 左问题卡右反馈列表；底部答题 composer。
- 提案：页壳顶栏 + 房间二级行（进度步骤条「题 2/5」+ 类别徽章 + 结束按钮）；问题卡题面大字号、focus_points 标签化、类别徽章带渐变点缀；反馈按时间分组、最新一条高亮；composer 卡片化（字数计数、语音按钮态变化、快捷键提示）；`<1024` 上下堆叠、反馈折叠、composer 吸底。

**报告页**
- 现状：header meta + 两列卡（综合表现 + 雷达 / 改进建议）+ 按类给分 `ul` + 逐题回放 `article` 平铺。
- 提案：**hero 区** = 综合分大数字（渐变点缀）+ 雷达图并排（**带生长动画**：面积由中心展开，`prefers-reduced-motion` 时直接呈现）+ 四维小分条；第二行 = 按类给分**卡片栅格**（类别徽章 / 分数或「样本不足」/ 题数 / 评语）；第三行 = 逐题回放改**折叠分组**（按主问题分组、追问缩进，默认展开第一题，含全部展开/收起）；改进建议卡带序号与强调样式。

**聊天页**
- 现状：260px 会话侧栏 + 主区（header 模型 select + 消息列表 + composer）。
- 提案：并入页壳顶栏；会话侧栏 token 化（hover/active/选中态渐变边）；消息气泡与 composer 复用面试间的新 composer 样式（消重复）；空态升级。

**设置页（AI 场景绑定）**
- 现状：裸 px/hex 的表格页（与 token 体系脱节的唯一页面）。
- 提案：token 全面重修；表格样式化（表头弱化、行 hover、状态徽章用 token 语义色）；保存按钮带状态反馈（保存中/已保存）；输入控件统一为样式化 Input/Select。

### 1.5 视觉语言要点

- 底色系：产品工具风（明亮浅色、圆角卡片、柔和阴影）；细节取 Linear 系（细边框、微妙渐变、高信息密度）。
- 字体：**系统字体栈**，靠字阶/字重/间距拉层次；不引 webfont。
- accent：蓝 → **靛蓝系**；渐变只做点缀（hero、综合分、类别徽章），不铺大面。
- 深浅色：浅色精修，深色随现有 `prefers-color-scheme` 机制同步（不并重精雕）。
- 动效：状态反馈（hover/active/focus、≤200ms transition、骨架屏）+ 进场/区块渐显 + 报告页雷达图生长动画（SVG 属性动画，CSS 实现）；所有动画必须有 `prefers-reduced-motion` 处理。

## 2. 不做

- **不换技术栈**（D24）：不引 Tailwind / shadcn / 组件库 / 动效库（动效库如需另立提案）。
- 不动业务逻辑、数据流、TanStack Query/zustand 用法、REST 契约（契约三件套只许不红，不许变）。
- 不加新页面（报告列表页、引导流程等一律范围外）；不改路由表。
- 不做移动端精雕（触控/手机断点）；不做视觉快照测试；不重构 `src/api`、`src/audio`、`src/stream` 逻辑层。
- 不动转写/答题的交互语义（MANUAL-TESTING §1.1–1.4 红线不许退化）。

## 3. 交付物

| 交付物 | 落点 |
| --- | --- |
| token 扩充与清漂移（假变量归零、靛蓝色阶、渐变/阴影/层级、断点约定） | `apps/web/src/styles/tokens.css` 及各 module.css |
| 页壳与顶栏（含导航高亮、用户区、响应式） | `apps/web/src/components/`（AppShell 族）+ `App.tsx` 接线 |
| 样式化组件补齐：Select / Input / Table / Badge / Skeleton | `apps/web/src/components/` |
| 5 条守卫脚本并接入 verify 的 web 契约层（会红） | `scripts/`（守卫脚本）+ `scripts/verify.sh` + 守卫自身测试 |
| 逐页版式改造（按 §1.4 线框） | `apps/web/src/pages/**` 各 module.css 与 JSX 布局 |
| 前后对照截图（后续整体设计阶段统一拍） | `docs/design/`（入库，兼作品集素材） |
| 手测清单更新（渲染半边 + hover/active 人工项） | `docs/MANUAL-TESTING.md` |
| 验收包 | `docs/tickets/p14-web-redesign/ACCEPTANCE.md` |

## 4. 测试与验收口径

### 4.1 测试缝（已与用户确认）

| 缝 | 测什么 | 先例 |
| --- | --- | --- |
| 既有逻辑测试保绿 | 172 例只增不减；tsc/eslint 门槛不松 | `pnpm -C apps/web test --run` |
| **带逻辑的新组件**行为单测 | 页壳导航高亮、折叠分组开合、Skeleton 开关等**外部可见行为** | 现有页面级测试（`ChatPage.test.tsx` 等 8 个） |
| **守卫 5 条**（先红后绿，守卫脚本自身要对坏输入红一次） | ① token 零假变量（引用的每个 --br-* 都有定义；--br-color-* / --br-gradient-* / --br-shadow-* 深浅双定义） ② 全 CSS 树零裸 hex/px（styles/tokens.css 除外，白名单注释制）③ 全站 ≥1 条宽度断点 ④ 动画与过渡必有 `prefers-reduced-motion` ⑤ 页面不裸用 `select/input/table` | `tests/test_verify_script.py` 的层图钉法；`check_scripts.py` 语法扫描族 |
| 纯样式 | **不写测试**（不引快照） | — |

「每个交互元素有 hover/active」**不进守卫**（判不了真伪）：进手测清单 + 评审口径。

### 4.2 阶段验收（两批，D25）

1. **基建批**：守卫 5 条红-绿证据 + 172 例/tsc/eslint 全绿；截图在后续整体设计阶段统一拍。
2. **页面批**：逐页「线框 vs 实现」对照（`docs/design/`）+ 手测渲染半边复验 + hover/active 人工项；截图在后续整体设计阶段统一拍。

### 4.3 复跑命令与回归底线

```bash
cd '/root/better resume' && pnpm -C apps/web test --run   # 172 例只增不减
pnpm -C apps/web lint && pnpm -C apps/web typecheck
bash scripts/verify.sh --layer all                        # 含新守卫（web 契约层）
bash scripts/compose_smoke.sh                             # 缓存头断言不红；改前端后 up -d --build nginx 核对新 hash
```

回归底线：既有 172 例不红；tsc/eslint 绿；契约三件套不红（REST 模型零改动）；`compose_smoke.sh` 不红；
MANUAL-TESTING §1.1–1.4（实时转写）红线不退化。

## 5. 预估

| 工作包 | 规模 | 说明 |
| --- | --- | --- |
| 基建批（token/页壳/断点/组件补齐/守卫） | M | 守卫先红后绿是重点；一次投入全页受益 |
| 页面批：报告页 + 上传页 | M | 作品集第一眼，hero 区与卡片栅格是主战场 |
| 页面批：面试间 | S–M | 结构不动，主要是层级与 composer |
| 页面批：聊天页 + 设置页 | S | 聊天页复用为主；设置页是清漂移的收尾 |
| 截图与文档 | S | 截图入库 + 手测清单更新 |

最大风险：① 每页「精致度」的主观阈值——用 §1.4 线框逐页点头前置锁死；② 改版碰 JSX 失手伤到转写/答题路径——用 172 例 + §1.1–1.4 手测红线兜底；
③ 守卫写成「恒绿的检查」——守卫脚本必须先对坏输入红一次（D22）。

## 6. 用户拍板结果（2026-10-12）

| # | 问题 | 决定 |
| --- | --- | --- |
| 1 | 线框逐页点头（§1.4 七块） | **确定**：页壳/登录门/上传页/面试间/报告页/聊天页/设置页全部按提案执行 |
| 2 | 报告页雷达图生长动画 | **同意推荐：做**（SVG 属性动画，reduced-motion 有守卫兜底） |
| 3 | 截图目录 | **确定**：`docs/design/`，按页面分子目录 |

（原问题留存：）

Q1 **线框逐页点头**（本提案 §1.4 的核心待批）：七个区块（页壳/登录门/上传页/面试间/报告页/聊天页/设置页）逐块确认或改；
也可以只批「基建批先行」，页面批的线框在基建验收后再逐页点头。

Q2 **报告页雷达图生长动画**（Q11 留给本阶段按成本定）：实现成本低（SVG 属性动画、CSS 即可、reduced-motion 有守卫兜底）。
➡️ 推荐：**做**，作为报告页 hero 的点睛；不做也只损失一点仪式感。

Q3 **截图目录** `docs/design/`（入库新目录）：阶段票据目录会在收口后移入 history，截图要放长期位置。
➡️ 推荐：`docs/design/`，按页面分子目录。