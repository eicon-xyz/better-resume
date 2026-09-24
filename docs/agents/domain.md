# Domain Docs

工程技能在探索代码库时应如何消费本仓库的域文档。

## 探索之前先读

- **`CONTEXT.md`**（仓库根）：域词汇表。**只有术语，不含实现细节**——不是 spec、不是草稿纸、不存放实现决策。
- **`docs/DECISIONS.md`**：本仓库的 ADR 存储（D01–D18…）。读与你即将改动的领域相关的决议行。
  - **替代模板默认的 `docs/adr/`**：新增决议**续编编号**（D19、D20…）追加进同一张表，并同步更新表标题的编号区间；**不新建 `docs/adr/` 目录**。
- 本仓库是**单上下文**（single-context）：没有 `CONTEXT-MAP.md`，也不设 per-package 的 `CONTEXT.md`。

如果 `CONTEXT.md` 不存在，**静默继续**：不要提示缺失、不要主动建议创建。
`/domain-modeling`（经 `/grill-with-docs` 触达）会在术语或决策真正落地时**懒创建**。

## 文件结构

```text
/
├── CONTEXT.md              ← 域词汇表（懒创建，只有术语）
├── CODING_STANDARDS.md     ← 评审期标准（`/code-review` 的 Standards 轴读它）
├── docs/
│   ├── DECISIONS.md        ← ADR 存储（本仓库特有，替代 docs/adr/）
│   ├── agents/             ← 本目录：技能配置
│   └── tickets/<stage>/    ← spec + 票据 + 验收包
├── apps/api/src/better_resume/
└── apps/web/src/
```

## 使用词汇表里的词

产出里凡是点名域概念的地方（票据标题、重构提案、假设、测试名），一律用 `CONTEXT.md` 里定义的词，
不要漂移到词汇表明确回避的同义词。

如果需要的概念还不在词汇表里，那是个信号：要么你在发明项目不用的语言（重新考虑），
要么是真缺口（记下来交给 `/domain-modeling`）。

## 与决议冲突时要显式指出

产出一旦与既有决议矛盾，**明确摆出来**，不要默默覆盖：

> _与 D04（不引 LangChain）冲突，但值得重开，因为……_
