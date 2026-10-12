# M4-T1 — 句池归并 AstTranscriptionAssembler（亮点③）

- blocking：M3
- 纪律：先写失败测试（红），再实现（绿）；**这是纯函数，测试穷举到每个协议分支**

## 目标

把 §4.4 的 `AstTranscriptionAssembler`（Java 内部类，TreeMap 句池）移植为 Python：
输入讯飞增量包（seg_id / pgs / rg / bg / ed / 文本），输出**三级文本快照**
`{full, committed, live, display, revision, segmentId, finalPacket}`。上层永远只看到 `replace/archive/final`。

## 交付物

- `media/models.py` 扩展：`TranscriptUpdate`（三级文本 + revision + 段元数据）、`TranscriptEvent` 增
  `kind: "replace" | "archive" | "final"` 与 `text`
- `media/assembler.py`：`SentencePool`（有序段表，等价 TreeMap<Integer segId>）+ `AstTranscriptionAssembler`
  - `apd`（追加）：段内追加文本
  - `rpl`（替换）：按 `rg` 删除区间（半开区间、越界保护）+ 写入新文本
  - **无 pgs 的包**：按 `bg/ed` 重叠度 ≥0.6 判同段；同段再按文本演化（公共前缀 ≥0.8 或互相包含）判定
  - 尾缀合并：新段与前段尾缀相同/包含时合并，避免"边打字边重复"
  - `committed` = 已定稿段拼接；`live` = display 剔除 committed 前缀；`final` 包提交并冻结段
  - `revision` 单调递增（前端据此丢过期帧）
- 测试：`tests/media/test_assembler.py`（≥20 例，逐条对应原反射单测语义）

## 测试（关键用例）

| 用例 | 断言 |
| --- | --- |
| apd 追加 | display 逐字增长；committed 不变；live == display |
| rpl 删区间 | 指定区间被替换，长度与内容符合预期；越界不抛异常 |
| 无 pgs 同段演化（前缀 ≥0.8） | 判为同段，replace 而非新增段 |
| 无 pgs 不同段（重叠 <0.6） | 新增段，句池按 seg_id 有序 |
| 尾缀重复 | 合并后不出现重复词 |
| final 包 | 该段进入 committed，live 剔除其前缀 |
| 乱序到达（seg 2 先于 seg 1） | 句池按 seg_id 有序重建，display 顺序正确 |
| revision | 每次输出严格递增；重复包 revision 不变（幂等） |
| 空文本 / 纯标点包 | 不产生空段、不崩 |

## 验收

| 命令 | 期望 |
| --- | --- |
| `uv run pytest -q tests/media/test_assembler.py` | 全绿 |
| 反例校验 | 去掉"无 pgs 演化判定"后，至少 3 个用例转红（证明测试有鉴别力） |

## 不做

- 不做标点恢复/顺滑（讯飞已给标点）；不做多语言混排特殊处理；不做草稿板（D09 砍）。

