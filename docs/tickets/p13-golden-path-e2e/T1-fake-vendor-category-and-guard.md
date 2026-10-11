# P13-T1 — 假供应商产出合法 category + 守卫要能红

- Status: ready-for-agent
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
