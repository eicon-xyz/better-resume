# M0 Kickoff Prompt（发给新会话的提示词，修订版）

先读（按序；读完先用 3-5 行复述你的理解，再动手）:
1. docs/DECISIONS.md 全文 —— D01–D17 是开工依据；§3「明确不做清单」是硬约束
2. docs/ai-meeting-architecture-analysis.md 仅读 §12.1（模块清单）与 §12.4（里程碑定义），
   不要通读全文

背景事实:
- 本仓库目前只有 docs/，还不是 git 仓库（先 git init）
- 本机 WSL2 Ubuntu-22.04；先检查工具链 python3.12 / uv / pnpm / node20 / docker，
  缺什么报告我，不要静默换方案
- 暂不建 GitHub remote，用本地 git：git init 后本地小步提交即可；
  CI 验收 = workflow 文件就位 + 本地以相同命令跑绿
  （将来建仓补 remote 再开 PR，不在本次范围）

本次范围: 仅 M0。M0 采用以下扩展定义（对 §12.4 的显式扩展，其余里程碑不动）:
- compose 仅 postgres + redis + api 三服务，全部带健康检查（api 暴露 /healthz）；
  worker / nginx 留给后续里程碑（对齐 D07 的最终形态，但本阶段不建）
- apps/api：settings（pydantic-settings + structlog + request_id）与
  identity（cookie session 骨架）做最小可用实现
- §12.2 有接口草图的六个模块（llm-gateway / ai-resilience / interview-engine /
  conversation / media / resume-parser）：Protocol 空接口 + 可导入的占位实现
- skills/ 知识库不在 M0（§12.4 归 M6），不要顺手建

约束:
- 遵守 DECISIONS.md §3 不做清单，清单外的东西不要顺手加
- 测试：M0 占位测试写「可导入 / 合约」通过型冒烟测试（保证 CI 绿）；
  红-绿 TDD 从 M1 第一张票据开始；只 mock 系统边界（LLM / 时钟 / Redis / 讯飞），
  不 mock 内部模块
- compose 开发凭证可用默认值并同步 .env.example；任何真实密钥必须走环境变量
  （原项目「密钥入库」是点名要避开的坏味道）
- 事实类问题（环境/文档）自己查；决策类问题提议选项等我确认；不要替我做决议
- 不要重新克隆或分析原 GitHub 仓库，分析结论都在 docs/ 里
- 单项连续失败 3 次或预计超 1 小时：停下汇报，不要硬扛

完成标准（逐条附执行证据：命令输出摘要或文件路径）:
- git init 完成；monorepo 结构符合 D08（apps/api / apps/web / docs / skills 占位）；
  小步提交，commit message 说 WHAT
- docker compose up 三服务全部 healthy（含 api /healthz）
- ruff + pytest + alembic check 本地全绿；eslint + tsc + vitest 本地全绿
- CI workflow 双 job 文件就位且语法校验通过
- 六个模块接口可从包外导入，且各有对应占位测试
- 我没有需要手动补的步骤（除确认决议）

产出与顺序:
1. 先交 M0 票据拆分提案：垂直切片、每张票据一次会话内可完成、标注 blocking 边；
   写入 docs/tickets/m0/（每张：标题 / 验收 / blocking）——等我确认后才动工写代码
2. 确认后按票据执行，最终交付可运行的 monorepo 骨架
3. 发现文档冲突或缺口：列出来 + 给修改建议 + 等我确认，不要自行改 docs/
