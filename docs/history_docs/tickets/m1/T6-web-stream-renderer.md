# M1-T6 — stream-renderer（事件解析 + 打字机 limiter）

- blocking：M1-T4

## 目标

把旧项目「`parseAiStreamChunk` + 两个 `TextStreamLimiter` + 过期 chunk 丢弃」三件套
合并成一个可单测的模块（§5.6 的 streamLimiter.ts 精神，40ms/12 字节奏）。

## 交付物

- `apps/web/src/stream/renderer.ts`：`createStreamRenderer({ onContent, onReasoning, onDone, onError })`
  - 双通道 limiter（content / reasoning 各一路，40ms 窗口、12 字步长，可配）
  - `push(event)` / `flush()` / `stop()`；`stop()` 后丢弃在途
  - 由外部传入「当前请求是否仍活跃」判定（`isActive()`），过期 chunk 直接丢（对应
    旧项目 activeStreamRequestId 校验）
- 测试（vitest，假时钟）：突发 500 字 -> 分帧平滑输出；reasoning 先到、content 后到不互相打断；
  `stop()` 后无回调；乱序/重复帧丢弃；`onDone` 一定在 flush 之后

## 验收

| 命令 | 期望 |
| --- | --- |
| `pnpm -C apps/web test` | limiter 用例全绿（假时钟驱动，无 sleep） |
| 长文本 500 字 @12 字/40ms | 输出被切成 >=40 帧且拼接后与原文完全一致 |

## 形态提议（待确认）

- limiter 用 `setTimeout` 链（不引 requestAnimationFrame，避免后台标签页停摆）。
- 打字机节奏沿用旧项目 40ms/12 字（Q7）。

## 不做

- 不做 Markdown 解析（在 T9 的渲染层做）；不做语音/光标动效引擎。
