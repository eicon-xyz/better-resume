# P13-T1 — 假供应商产出合法 category + 守卫要能红

- Status: done（红绿已过，待用户验收）
- Blocked by: 无
- 唯一写入路径：`apps/api/scripts/fake_openai.py` 与 `apps/api/tests/test_fake_openai.py`

> 阶段：P13（假模型驱动的黄金路径 E2E）。依据 `README.md` §1.2 现状表与 §1.3。
> Q2 已定：**保留**「不给 `category`」的形态（按 prompt 标记切换），且两个模式都必须被某一层真的跑到。
> 纪律：先写会红的用例，再写最小实现（垂直切片）；只 mock 系统边界；断言走公开行为。
## 目标

`apps/api/scripts/fake_openai.py:56-67` 的 questions payload 只有 `topic` / `focus_points` / `text`，**没有 `category`**。
按 D23，缺失会走规则回退——所以 P11 之后所有走假供应商的检查，测的都是回退路径，不是「模型给出合法类别」那条主路径。

而 `fake_openai.py:25-26` 自称「`tests/test_fake_openai.py` validates every payload against the real pydantic contracts,
so the fake cannot silently drift」——**守卫没拦住**，因为字段可空时缺字段也能通过校验。

## 红-绿切片

| # | 用例 | 断言 |
| --- | --- | --- |
| 1 | 守卫能抓住受控字段缺失（**先写这条，它必须先红**） | 从 payload 里去掉 `category` → 守卫测试失败；不是「解析成功就算过」 |
| 2 | questions payload 带合法 category | 每条的 `category` ∈ {`fundamentals`, `project`, `internship`} |
| 3 | 守卫覆盖契约里**所有**受控枚举字段，不只 category | 新增一个受控枚举字段而 fake 不给 → 守卫红（用参数化或反射，别写死字段名清单） |
| 4 | 若 Q2 选「保留无 category 形态」 | 两种形态都能被显式选择，且**都被某一层跑到**（不许留默认关闭没人跑的分支） |

## 红线

- 只写这两个文件；不动引擎、不动 `prompts.py` 的 schema、不动 `compose.yaml`。
- 守卫必须**真的会红**：只打印结论、不判定的检查视为缺陷（D22）。交付前自己把 `category` 删掉跑一次，把红贴进验收包。
- 不新增依赖。不写「本次新增」这类历史叙述（硬规则 2）。
- 与 spec 冲突或信息不足 → **停下来报**。

## 验收

| 命令 | 期望 |
| --- | --- |
| `cd apps/api && uv run pytest -q tests/test_fake_openai.py --junitxml=/tmp/f.xml` | 全绿；例数看 xml 读数 |
| 手动把 `category` 从 payload 删掉后重跑 | **必须红**；把红的原始输出贴进验收包，然后恢复 |
| `uv run ruff format --check . && uv run ruff check .` | 通过 |
| `grep -n category apps/api/scripts/fake_openai.py` | 命中 payload 构造处 |

## 不做

- 不改真供应商适配器；不改 `QuestionBatch` 的 schema；不动 `scene_for` 的嗅探规则（除非 Q2 需要新的切换标记）。

## 意图复述

本票要解决两件事：一是让假供应商 `fake_openai.py` 的 questions 场景产出携带合法 `category` 的 `QuestionBatch`，
使后续黄金路径 E2E 走的是「模型给出类别」的主路径而非 D23 的规则回退；二是把 `tests/test_fake_openai.py` 的防漂移守卫
从「能被 pydantic 解析」收紧为「契约里的受控枚举字段在 payload 里出现过合法值」——因为字段可空时缺字段也能解析通过，旧守卫拦不住。

做法：先写一条会红的守卫用例（反射枚举 `GeneratedQuestion` 的受控枚举字段，要求 payload 每条都给出合法值），当前 payload 无 `category`，
它必须先红；再在 `_question_payload` 里最小实现补上合法 `category` 让它绿。守卫用反射而非字段名清单，新增受控枚举字段而不给值必须能让它红。
按 Q2 保留「不给 category」的形态：在 prompt 里用一个显式标记切换到该形态，两种形态都用测试覆盖其选择机制。

不做：不动引擎与 `prompts.py` / `QuestionBatch` 契约、不动 compose、不改真供应商适配器、不动 `scene_for`；
不把任一种形态接进 verify 层（后续票的事）；不 commit。

## 实现决定交代

| spec 未覆盖、我自行拍定的决定 | 为什么这么拍 | 我明确没做的 |
| --- | --- | --- |
| 切换标记形态：`NO_CATEGORY_MARKER = "不给出 category"`，出现在 prompt 里即切到「不给 category」形态；不出现则给 category | 沿用 `scene_for` 的 prompt 嗅探风格（中文字样），不引入请求头/参数等新协议；同一个 `completion_payload(text)` 入口即可显式选择两种形态 | 没给「给 category」另造一个正向标记——它的选择就是「不写标记」，由默认形态承担 |
| 类别分配：题间循环 `fundamentals` → `project` → `internship`（`(index - 1) % 3`） | 票只要求每条落在三枚举内；fake 不解析配比提示。循环让三种类别都出现，供后续 E2E 的报告分类覆盖 | 没有按 `render_mix` 的配比分配——那要解析配比提示，超出本票 |
| 守卫范围：反射扫描 fake 所服务的四份契约（`QuestionBatch` / `ScoreResult` / `FollowUpQuestion` / `ReportSummary`），并递归子模型 | 票据要求「契约里所有受控枚举字段」，四份是 fake 实际回答的全部 shape；递归使根模型或嵌套模型新增枚举字段都会被抓 | 没写字段名清单；没改契约真实模型 |
| 守卫读原始 payload（存在性 + 合法值），在 pydantic 校验之前判定 | 可空字段缺失时 pydantic 仍能解析；本票的核心就是堵住这个漏检 | 没有只断言「能解析」 |
| 「新增字段 → 守卫红」的证明：测试内定义一次性 `_ExtendedQuestion`（继承 `GeneratedQuestion` 并加一个 `_Seniority` 枚举字段）喂给守卫 | 红线禁止改 `prompts.py` 的 schema，用测试内探针证明反射会捕获未见过的受控字段 | 没有去改真实契约制造红 |
| 「不给 category」形态豁免守卫：守卫只跑给 category 的规范形态；无 category 形态由单独测试覆盖 | Q2 明确保留回退形态，它本就不该带 category；D22 的「会红」由删掉规范形态的 category 来演示 | 没有把无 category 形态接进 verify 层或引擎 |
