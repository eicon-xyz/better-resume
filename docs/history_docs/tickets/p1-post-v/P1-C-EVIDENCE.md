# P1-C 验收包：以阿里 API 替代讯飞/星云真机（用户指令 2026-09-15）

- 票据：`docs/tickets/p1-post-v/README.md` §2 P1-C（**范围已变更**）；分支 `p1/realtime-asr`
- 结论：**完成（含一处书面边界），待用户验收**。原票两个"无凭据验不了"的缝，用同一把百炼 key 的等价能力验证；
  讯飞 AST / 星云工作流本身仍标"环境不具备"。

## 1. 范围变更

| 原计划 | 改版后（阿里 API） | 状态 |
| --- | --- | --- |
| 讯飞 AST 真机（流式 ASR + 句池归并） | 阿里 Paraformer 实时：多句真机（适配器级）+ 真机增量包回放句池 | ✅ 见 §2/§3 |
| 星云工作流真机 | 阿里等价物 = **百炼应用调用**（app_id 形态），需你在百炼控制台建应用并给 app_id | ⏸ **待你提供 app_id**（不假装验证过） |

## 2. C1a：多句真机验证（适配器级，1 次真调用）

音频：`data/audio/p1c-multi-sentence-16k.wav`（edge-tts 合成 13.1s / 3 句；本机无 ffmpeg，转码用 soundfile）。
命令：`uv run python scripts/media_smoke.py --paraformer-rt-real --wav ../../data/audio/p1c-multi-sentence-16k.wav`

| 指标 | 结果 |
| --- | --- |
| 事件序列 | **replace 20 + archive 3（逐句）+ final 1**；首增量 **0.50s** |
| 分段正确性 | 每句单独 archive；final = 三句正确拼接 |
| **供应商自我纠错** | 实测 `第二句。街` → `第二句街口响` → … → `第二句接口响应时间从800毫秒降到了2` → archive 为正确全句——**整句重写**，这正是 `replace`（重写 live 区）存在的理由，也是 M4 合并规则必须"整段替换"而非"追加"的真机证据 |
| 已知 ASR 误识 | 供应商把"限流"听成"线流"（合成音导致，非我方缺陷，如实记录） |

## 3. C1b：真机增量包回放句池归并（`scripts/assembler_real_probe.py`，1 次真调用）

把真实 `result-generated` 帧按 `AstPacket(pgs=None, text, bg, ed, final=sentence_end)` 回放（"供应商重发句子"正是该分支的语义），喂 `AstTranscriptionAssembler`：

| 指标 | 结果 |
| --- | --- |
| **提交语义** | `pool.committed_text()` **完全等于**供应商归档文本（三句全对）→ **PASS** |
| **已知边界** | `pool.ordered()` = **26 段**（真实 3 句）：live 区保留了所有未匹配的中间改写。原因是 `_match_open_segment` 依赖 `time_overlap + evolves()`，而阿里式句中改写（`第二句。街`→`第二句街口响`）既非前缀也非演化 → 每片新建段 |
| 为什么不是线上 bug | 没有任何生产路径把该供应商喂进句池：`paraformer-rt` **直连 replace/archive**（P1-A），句池服务的是讯飞 AST 包型。该边界反过来证明了 P1-A 的设计选择是必要的 |
| 回归护栏 | 探针断言"提交文本 == 供应商归档"；若未来句池学会合并阿里式改写（或提交语义被破坏），探针会翻转 |

## 4. 未验证项（诚实清单）

1. **讯飞 AST 真机**：仍无凭据，未验证（本次用阿里实时 ASR 覆盖同类能力，非同一协议）。
2. **星云工作流真机**：未验证；阿里等价物（百炼应用调用）**待 app_id**。
3. 句池对"阿里式改写"的合并能力：不合并（见 §3 边界），也**不打算**改——生产路径不需要。

## 5. 复跑

```bash
cd '/root/better resume/apps/api' && export PATH="$HOME/.local/bin:$PATH"
uv run python scripts/media_smoke.py --paraformer-rt-real --wav ../../data/audio/p1c-multi-sentence-16k.wav
uv run python scripts/assembler_real_probe.py          # 各 1 次真调用，注意花费
```
