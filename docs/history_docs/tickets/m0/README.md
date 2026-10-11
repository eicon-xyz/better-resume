# M0 票据拆分提案（待确认）

> 依据：docs/DECISIONS.md（D01–D17）+ docs/ai-meeting-architecture-analysis.md §12.1/§12.4
> + docs/M0-kickoff-prompt.md 的 M0 扩展定义。
> 状态：**提案，等你确认后动工**。确认方式：整包确认，或指出要改的票据/形态项。

## 1. 范围边界（M0 只做这些）

- compose 三服务：postgres + redis + api，全部带健康检查（api 暴露 `/healthz`）；worker / nginx 不建。
- apps/api：settings（pydantic-settings + structlog + request_id）+ identity（cookie session 骨架）最小可用。
- §12.2 有接口草图的六个模块：llm-gateway / ai-resilience / interview-engine / conversation /
  media / resume-parser —— Protocol 空接口 + 可导入占位实现 + 冒烟测试。
- apps/web：Vite + React 19 + TS 骨架，eslint / tsc / vitest 三绿（业务模块留 M1）。
- CI 双 job 文件就位 + 本地同命令跑绿。
- **不做**：skills 知识库内容（M6）、interview-report 实现（M2）、任何真实 LLM/ASR 调用、
  Redis 分布式单飞 Lua、JWT、OpenTelemetry、LangChain（DECISIONS §3 硬约束）。

## 2. blocking 图（箭头 = 被阻塞方等待箭头源）

```
T1 仓库地基
 \-> T2 api 骨架 + settings + /healthz
      +-> T3 identity cookie session
      +-> T4a 模块契约（core 三件）
      +-> T4b 模块契约（domain 三件）
      +-> T6 compose 三服务 -\-> T5 alembic 基线（需要真 Postgres 实例）
 T1 -\-> T7 web 骨架
 T2 + T3 + T5 + T6 + T7 -\-> T8 CI 双 job
 全部 -\-> T9 M0 验收汇总（证据）
```

| 票 | 标题 | blocking | 预估 |
| --- | --- | --- | --- |
| T1 | 仓库地基与工具链固定 | — | 0.5 会话 |
| T2 | apps/api 骨架 + settings + /healthz | T1 | 1 会话 |
| T3 | identity cookie session 骨架 | T2 | 1 会话 |
| T4a | 模块契约：conversation / llm-gateway / ai-resilience | T2 | 1 会话 |
| T4b | 模块契约：interview-engine / resume-parser / media | T2 | 1 会话 |
| T5 | DB 连接 + Alembic 基线（alembic check 绿） | T6 | 0.5 会话 |
| T6 | compose 三服务 + 健康检查 | T2 | 1 会话 |
| T7 | apps/web 骨架（lint/tsc/vitest） | T1 | 1 会话 |
| T8 | CI 双 job + 本地等价命令验证 | T2 T3 T5 T6 T7 | 0.5 会话 |
| T9 | M0 验收证据汇总 | 全部 | 0.5 会话 |

## 3. 每票验收约定

- 只 mock 系统边界（LLM / 时钟 / Redis / 讯飞），不 mock 内部模块（kickoff 约束）。
- M0 测试是「可导入 / 合约」通过型冒烟测试，红-绿 TDD 从 M1 第一张票据开始。
- 小步提交，commit message 说 WHAT（英文祈使句，如 `Add api skeleton with healthz`）。
- 证据形式：命令 + 退出码 + 输出摘要（写进 T9 的 ACCEPTANCE.md）。

## 4. 本提案附带的待确认项

见 `OPEN-QUESTIONS.md`（工具链安装、git 身份、端口、skills 占位、CI node 版本等）。
