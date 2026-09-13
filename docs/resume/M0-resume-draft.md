# 简历草稿（M0 骨架期）

> D14 硬规则：每个里程碑结束更新一次简历草稿。
> 口径原则：**只写已经跑通、可演示的东西**；未实现的能力只列「承接计划」，不写成成果。

## 1. 本阶段可写的条目（有执行证据）

- 单仓库 monorepo 工程地基：Python 3.12 + uv 与 pnpm 双工具链、锁文件入库、
  MIT 许可、GitHub Actions 双 job（ruff + pytest + alembic check / eslint + tsc + vitest），
  10 条小步提交，99 个受版本控制文件。
- 容器化本地环境：docker compose 三服务（Postgres 16 / Redis 7 / FastAPI）全部带健康检查，
  `/healthz` 供编排探活；开发凭证走 `.env.example`，密钥零入库。
- 后端可观测性与身份地基：structlog JSON 日志 + request_id 贯穿（contextvar 绑定/透传/响应头），
  HttpOnly Cookie 会话（Redis 存储、30 天滑动过期、SameSite=Lax），登出即失效。
- 模块化单体的接口先行：六个深模块（conversation / llm-gateway / ai-resilience /
  interview-engine / resume-parser / media）以 Protocol + Pydantic 类型锁定接缝，
  占位实现显式报错而非静默，合约测试逐方法校验签名。

## 2. 旧简历亮点承接计划（对应 D01 / D16）

| 旧项目亮点 | 新承接物 | M0 状态 | 可写成亮点的时点 |
| --- | --- | --- | --- |
| 五阶段 Prompt Pipeline | interview-engine 状态机 + 每阶段独立可测 | 接口就位 | M2 |
| Agent 追问不编造数据 | 追问裁决纯函数 + missing_points + schema 强校验 | 类型就位 | M2 |
| FastAPI + SSE + 15s 心跳 | 对话/面试/语音三链路 | 未开始 | M1/M4 |
| LLM 统一工厂层 | llm-gateway 模型注册表 + 运行时切换 | 接口就位 | M1/M5 |
| 混合策略简历解析 | resume-parser（pdfplumber + 启发式 + CJK 回退） | 接口就位 | M2 |
| （新增）单飞 + 熔断 + 限流 | ai-resilience.run() 一个方法承担三层互斥 | 接口就位 | M3 |
| （新增）ASR 句池归并增量去重 | media XunfeiAstAdapter | 接口就位 | M4 |

## 3. 下一里程碑要补的证据（M1）

- 打字机式对话 + reasoning_content 分流面板 + 历史回放（可截图的演示）
- conversation 真表（Postgres + JSONB）与 seq 原子性测试
- llm-gateway OpenAICompatAdapter 的契约测试（录制/回放真实响应）
- OpenAPI → TS 类型生成打通（根治前端猜字段，D17）

## 4. 待你确认

- 旧简历原文的措辞口径（需要你提供旧简历文件，M0 未拿到）
- 是否把「工程地基」这类条目写进最终简历，还是只留三大深挖件（D16）
