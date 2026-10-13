# P14-T11 — 登录门 hero 化（补漏票）

- Status: ready-for-agent
- Blocked by: 无
- 唯一写入路径：`apps/web/src/pages/LoginGate.tsx`、`apps/web/src/pages/LoginGate.module.css`、本票与 `T11-EVIDENCE.md`

> 依据 README §1.4「登录门（首屏）」线框、§1.5 视觉语言要点、§4.1 测试缝（纯样式不写测试）；D24 / D25。
> 线框七块已逐块确认（README §6 决策 1）；README §1.4「登录门」一块在页面批无承接票，由用户裁定补做，本票即该块的施工规格。
> 纪律：不改登录行为语义、不加新依赖、不 commit；先红后绿——本票无新可观察行为，红-绿落在守卫变异（见验收）。

## 目标

1. **全屏门面**：登录门撑满 AppShell 内容区，并横向全出血抵消内容容器的 max-width；底色改为低饱和靛蓝渐变，用既有 token 组合 `--br-color-accent-muted → --br-color-bg`，不新增渐变 token。
2. **居中 hero**：大字阶产品名 `better-resume`（`--br-text-hero`，42px，`--br-gradient-hero` 渐变文字）＋ 一句话价值主张。
3. **玻璃质感登录卡**：半透明表面（独立表面层 `opacity`，不牵连文字）＋ 发丝边框 ＋ `--br-shadow-md` 柔阴影；卡内是用户名输入（`Input`，等价替换原 `Textarea rows=1`）＋「进入」按钮。
4. **行为零退化**：`login.mutate` 的调用、demo 兜底、`登录失败：…` 错误语义、`loading` 态、`aria-label="用户名"` 全部原样；Tab 可达与「Enter 不提交」语义不变。

## 红线

- `login.mutate` 的调用点、`userId.trim() || "demo"` 兜底、`role="alert"` 的「登录失败：…」文案、`loading`/`aria-busy` 态、用户名输入的可访问名（`aria-label="用户名"`）一律不改。
- 用户名输入只做 Textarea rows=1 → 样式化 Input 的等价替换；不新增提交行为（不做 Enter 提交、不包 form）。
- 不改业务逻辑、数据流、路由、REST 契约、`components/`、`styles/`、`src/api|audio|stream|chat`、守卫脚本/测试/`verify.sh`、README、T1–T10 票与既有 EVIDENCE。
- 不改既有测试断言（`ChatPage.test.tsx` / `InterviewIntroPage.test.tsx` 的登录门断言）；这两个文件不在写入路径。
- 不新增依赖、不引 webfont 或动效库；token 只用现有集合（47 个 + `--br-text-hero`）；`allow:` 白名单维持 41 条不增；不 commit、不截图。

## 验收

| 命令 | 期望 |
| --- | --- |
| `python3 scripts/check_web_style_guards.py` | exit 0，末行 `check_web_style_guards: ok` |
| `grep -rn 'allow:' apps/web/src \| wc -l` | 41（不增） |
| `pnpm -C apps/web test --run` | ≥202 passed（只增不减） |
| `pnpm -C apps/web typecheck`、`pnpm -C apps/web lint` | exit 0 |
| `git diff --numstat -- apps/web/src/pages/ChatPage.test.tsx apps/web/src/pages/InterviewIntroPage.test.tsx` | 空输出（既有登录门断言零改动） |
| `bash scripts/verify_mutation.sh` | 把 hero 渐变消费改成未定义 token → 守卫①红并点名 `LoginGate.module.css` → 恢复绿；恢复后 sha256 / `cmp` 逐字节一致 |
| `bash scripts/verify.sh --layer all` | 末行 `ALL PASS (… commands)`，exit 0 |

纯样式不新增单测：输入控件是等价替换，没有新可观察行为，红-绿由守卫变异承担；键盘可达与「Enter 不提交」语义由既有页面测试与人工手测兜底。

## 不做

- 不改 AppShell（顶栏与内容容器不在写入路径），因此「全屏」的作用域是 AppShell 内容区，见 `T11-EVIDENCE.md` §五 的偏差说明。
- 不做移动端精雕、不引视觉快照测试；不新增渐变铺面（渐变仍只做 hero / 综合分 / 类别徽章三处点缀）。
- 不改守卫脚本与守卫测试、不改 README 与 T1–T10 材料。
