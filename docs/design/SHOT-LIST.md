# P14 拍摄机位清单（线框 vs 实现）

- **状态：线框 7 张已交付，实现侧已拍 10 张、待拍 4 个机位。** 逐机位实拍情况见下表「状态」列；未拍的机位不落空图占位。
- 用途：为 `docs/design/` 提供每页「线框（P14 README §1.4 文字稿）vs 实现」对照的固定机位，拍出的图兼作品集素材。
- 依据：P14 README §1.4 七块线框（逐块已获用户确认）、T9 票面。

## 红线（拍摄前必读）

- 截图里**不许出现真实简历内容**：简历一律用合成简历——姓名 / 公司 / 项目 / 联系方式全部为示例文本，无真实个人信息。
- 面试间与报告页的数据来自**用合成简历跑出的样例会话**；不得截入真实账号、真实邮箱、真实凭据或任何密钥。
- 设置页只拍脱敏行；凭据输入框内不留真实值。

## 目录与命名

```text
docs/design/
├── README.md          # 目录用途与命名约定
├── SHOT-LIST.md       # 本文件
├── shell/             # 页壳与顶栏
├── login-gate/        # 登录门
├── upload/            # 上传页
├── interview-room/    # 面试间
├── report/            # 报告页
├── chat/              # 聊天页
└── settings/          # 设置页
```

- 线框：每页子目录内一对 `wireframe-light.svg`（源，按 P14 README §1.4 文字稿等比例重构）+ `wireframe-light.png`（`convert -background none -density 144 <svg> <png>` 渲染，1920×1284）。
- 实现：现有实拍文件名为 `desktop-*.png`（`desktop-light` / `desktop-empty` / `desktop-topbar` / `desktop-q1` / `desktop-hero` / `desktop-categories-replay` / `desktop-replay-followups` / `desktop-bindings`）与 `select-options.png`；深色 `implemented-dark.png`、窄屏 `implemented-narrow.png` 尚未产生。
- 已拍 / 待拍在机位表的「状态」列出，已拍行同时给出文件名与像素尺寸；未拍一律写「待拍」。

## 机位口径

- 视口：桌面 **1280×800** 为主；窄屏 **390×844** 抽测（每页最多一张，横切塌缩另计）。
- 主题：**浅色为主**；深色每阶段抽 1–2 张，不为每页都拍。
- 浏览器：Chrome、缩放 100%、系统字体；本项目只验过 Chrome。
- 前置状态：登录用任意用户名（如 `demo`）；报告页与面试间用合成简历跑出的样例会话与报告数据。

## 机位表

| 机位 | 页面（路由） | 前置状态 | 视口 | 主题 | 拍摄要点 | 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| SH-01 页壳线框 | 全局 | — | 1280×800 | 浅色 | 顶栏（产品名 + 主导航 + 用户区/退出）+ 居中内容容器；一张图说清页壳 | 已交付（`shell/wireframe-light.svg` + `.png`） |
| SH-02 页壳实现 | 任意页（/chat） | 已登录 | 1280×800 | 浅色 | 顶栏 + 内容容器；导航选中态；右上用户区 | 已拍（`shell/desktop-topbar.png`，1914×57，仅顶栏裁切条） |
| SH-03 登录门线框 | 首屏门（未登录） | 未登录 | 1280×800 | 浅色 | 全屏门面：渐变背景 + hero（产品名 + 一句话）+ 登录卡 | 已交付（`login-gate/wireframe-light.svg` + `.png`） |
| SH-04 登录门实现 | 首屏门（未登录） | 未登录 | 1280×800 | 浅色 | 登录卡、输入、`进入`；纯键盘可达 | 已拍（`login-gate/desktop-light.png`，1919×882） |
| SH-05 上传页线框 | /interview | 已登录 | 1280×800 | 浅色 | 主区 7fr:5fr；dropzone 主视觉；侧列预览；继续列表卡片行；空态 | 已交付（`upload/wireframe-light.svg` + `.png`） |
| SH-06 上传页实现·空态 | /interview | 已登录、无历史会话 | 1280×800 | 浅色 | dropzone 主视觉 + 支持格式 + 侧重 Select + 空态 | 已拍（`upload/desktop-empty.png`，1919×931） |
| SH-07 上传页实现·有历史 | /interview | 已登录、有 ≥2 条合成简历会话 | 1280×800 | 浅色 | 继续列表卡片行（时间 / 状态徽章 / 继续） | 已拍（`upload/desktop-history.png`，1915×699） |
| SH-08 面试间线框 | /interview/room/:sessionId | 合成简历样例会话进行中（有 ≥2 条反馈） | 1280×800 | 浅色 | 二级行步骤条 + 问题卡 + 反馈列表 + composer | 已交付（`interview-room/wireframe-light.svg` + `.png`） |
| SH-09 面试间实现 | /interview/room/:sessionId | 同上 | 1280×800 | 浅色 | 步骤条「题 X / Y」+ 类别徽章；最新反馈高亮；composer 卡片 | 已拍（`interview-room/desktop-q1.png`，1910×928；第 1 题、无最新反馈高亮） |
| SH-10 面试间实现·深色 | /interview/room/:sessionId | 同上 | 1280×800 | 深色 | 深色下最新反馈高亮与 composer 对比度 | 待拍 |
| SH-11 报告页线框 | /interview/report/:sessionId | 合成简历样例报告（含 1 个「样本不足」类别） | 1280×800 | 浅色 | hero（综合分 + 雷达 + 四维小分条）+ 按类卡片 + 逐题折叠 | 已交付（`report/wireframe-light.svg` + `.png`） |
| SH-12 报告页实现·生长终态 | /interview/report/:sessionId | 同上 | 1280×800 | 浅色 | 生长动画结束后：综合分、雷达、四维小分条、按类栅格 | 已拍（`report/desktop-hero.png`，1889×851） |
| SH-13 报告页实现·逐题折叠 | /interview/report/:sessionId | 同上 | 1280×800 | 浅色 | 默认展开第一组；追问缩进；全部展开/收起 | 已拍（`report/desktop-categories-replay.png` 1669×805、`report/desktop-replay-followups.png` 1902×863） |
| SH-14 报告页实现·深色 | /interview/report/:sessionId | 同上 | 1280×800 | 深色 | 综合分渐变文字与雷达在深色下的可读性 | 待拍 |
| SH-15 聊天页线框 | /chat | 已登录、有 ≥2 条合成会话 | 1280×800 | 浅色 | 页壳顶栏 + 会话侧栏（页内二级栏）+ 消息列表 + composer | 已交付（`chat/wireframe-light.svg` + `.png`） |
| SH-16 聊天页实现 | /chat/:sessionId | 同上，选中有消息的会话 | 1280×800 | 浅色 | 侧栏选中态；用户/AI 气泡同配方；composer 字数与快捷键提示 | 待拍 |
| SH-17 聊天页实现·空态 | /chat | 已登录、无会话 | 1280×800 | 浅色 | 主区居中空态 | 已拍（`chat/desktop-empty.png`，1914×942） |
| SH-18 设置页线框 | /settings/ai | 已登录 | 1280×800 | 浅色 | 场景绑定表格 + 保存按钮状态反馈 | 已交付（`settings/wireframe-light.svg` + `.png`） |
| SH-19 设置页实现 | /settings/ai | 已登录、含已配置与未配置行 | 1280×800 | 浅色 | 表头弱化、行 hover、状态徽章、保存反馈；凭据脱敏 | 已拍（`settings/desktop-bindings.png`，1895×706） |
| SH-20 横切·窄屏塌缩 | /chat 与 /interview/room/:sessionId | 已登录 | 390×844 | 浅色 | 无水平滚动条；侧栏顶部折叠；两列塌单列；composer 吸底 | 待拍 |

## 已拍与待拍说明

- 线框侧：SH-01 / 03 / 05 / 08 / 11 / 15 / 18 七张已交付，均为 `docs/design/<页面>/wireframe-light.svg` + `wireframe-light.png` 成对。
- 实现侧已拍 10 张，落盘文件名与机位不完全同名（见「目录与命名」），实拍文件与机位对照：

  | 实拍文件 | 尺寸 | 对应机位 |
  | --- | --- | --- |
  | `shell/desktop-topbar.png` | 1914×57 | SH-02（仅顶栏裁切条，非整页） |
  | `login-gate/desktop-light.png` | 1919×882 | SH-04 |
  | `upload/desktop-empty.png` | 1919×931 | SH-06 |
  | `upload/desktop-history.png` | 1915×699 | SH-07 |
  | `upload/select-options.png` | 678×186 | 侧重 Select 展开态，机位表未单列 |
  | `interview-room/desktop-q1.png` | 1910×928 | SH-09（第 1 题，无最新反馈高亮） |
  | `report/desktop-hero.png` | 1889×851 | SH-12 |
  | `report/desktop-categories-replay.png` | 1669×805 | SH-13（按类栅格 + 逐题回放） |
  | `report/desktop-replay-followups.png` | 1902×863 | SH-13（追问缩进与展开态） |
  | `chat/desktop-empty.png` | 1914×942 | SH-17 |
  | `settings/desktop-bindings.png` | 1895×706 | SH-19 |

- 实现侧待拍 4 个机位：SH-10（面试间深色）、SH-14（报告页深色）、SH-16（聊天页有消息态）、SH-20（窄屏塌缩）。
- SH-02 需重拍整页口径：现有 `shell/desktop-topbar.png` 只是顶栏裁切条，不含内容容器与导航选中态。
- 实拍文件的视口尺寸不统一（1669–1919 px 宽），与机位表「1280×800」的约定不符；是否重拍由用户裁定。
