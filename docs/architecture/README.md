# 系统架构图（实时）

**`ARCHITECTURE.html` 是渲染产物，不要手改**——和 `docs/audit/MODULE-AUDIT.html` 同一条线：
数据/结构改脚本，HTML 每次重渲染覆盖。

- 生成器：`scripts/build_architecture_map.py`（只用标准库，`python3` 直接跑，无第三方依赖）
- 产物：`docs/architecture/ARCHITECTURE.html`（单文件、无外链、深色「终端蓝图」风格）

## 怎么用

| 目的 | 命令 |
| --- | --- |
| 渲染一次（含实时探针） | `python3 scripts/build_architecture_map.py` |
| **实时图**：每 5s 重渲染 | `python3 scripts/build_architecture_map.py --watch -i 5` |
| 只取仓库事实（不碰 docker / 网络） | `python3 scripts/build_architecture_map.py --no-probe` |
| 排版自检（重叠 / 穿盒 / 越界，看退出码） | `python3 scripts/build_architecture_map.py --check` |

浏览器里点「自动刷新：关」→ 开（或在地址后加 `?auto=1`），页面就跟着 `--watch` 的重渲染自动重载。
不跑 `--watch` 时页面是一张快照，页头会明确写「○ 快照」。

## 图里什么是自动的

- **结构事实**（每次渲染扫描仓库）：模块文件数/行数、HTTP 路由、ORM 表名、Redis 键名、
  LLM 场景与适配器、compose 服务与 profile、web 路由、git HEAD。
- **运行状态**（实时探针）：`docker ps -a`（按 compose 项目标签）→ 容器状态与健康；
  TCP 127.0.0.1:8080 / 5433 / 6379；HTTP `/healthz`、`/nginx-healthz`。
  **探针拿不到就写「未知」，不编造**（见 AGENTS.md 开发规范·证据诚实）；`--no-probe` 时整页标「未探针」。
- **手写部分**：只有排版坐标与每条线的走向（`build_nodes` / `build_wires`）与少量说明文案。

## 改架构时怎么维护

1. **服务 / 端口 / profile 变化**：不用改脚本——`compose.yaml` 是唯一事实源。
2. **路由 / 表 / Redis 键 / LLM 场景 / 适配器变化**：不用改——渲染时扫描源码。
3. **模块增删**：改 `MODULE_TARGETS` 与 `build_nodes` 的模块网格（文件数/行数自动跟）。
4. **只动视觉**（坐标、连线、文案）：改完跑 `--check` + 重新渲染一次，别手改 HTML。

## 约定

- 颜色只标**图层**：蓝 = 客户端、青 = 边缘/接入、绿 = AI 与韧性、琥珀 = 数据与异步、紫 = 语音与媒体、
  灰虚线 = 外部依赖；**红色只用于错误路径**（如 503 + Retry-After）。
- 状态徽标：● 运行中（绿色软脉冲）/ ▲ 异常 / ◐ 进行中 / ■ 已停止 / ○ 未创建 / ✓ 已完成。
- 实线 = 同步调用，虚线 = 异步或「展开视图」；每条线都有小字标签，拐点有小圆点。
