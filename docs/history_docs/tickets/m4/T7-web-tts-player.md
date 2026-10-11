# M4-T7 — 单例播放器（题目播报）

- blocking：M4-T4
- 纪律：先写失败测试（红），再实现（绿）；音频元素是系统边界，测试里用假 Audio

## 目标

D15「一个播放器」：题目播报只有一个 `Audio` 实例、一份 Blob 缓存，谁先点谁播，切换题目自动停旧的。

## 交付物

- `src/audio/ttsClient.ts`：`synthesize({text, voice})` → `{url, cached}`（走后端 T4 端点）
- `src/audio/player.ts`：单例播放器
  - `primeFromGesture()`：首次用户手势时播 1s 静音 wav 解锁 autoplay（照 §7.5 的教训）
  - `play(text, {voice, cacheKey})`：缓存命中直接播；未命中先合成（loading 态）
  - `canplaythrough` 3s 超时保护；播放失败（autoplay 被拦、格式不支持）→ 明确错误提示
  - `stop()` / 切题自动停；卸载时 `revokeObjectURL` 全部 Blob
- `src/audio/useTtsPlayback.ts`：React 绑定（`playing`/`loading`/`error` 状态 + `speak(text)` 方法）
- `src/pages/interview/RoomParts.tsx`：`QuestionCard` 增"朗读题目"按钮（播放中变"停止"）
- 测试：`player.test.ts`（假 Audio + fake timers，≥8 例）

## 测试

| 用例 | 断言 |
| --- | --- |
| 单例 | 连续播两段 → 只有一个 Audio 实例；第一段被 stop |
| 缓存 | 同文本第二次播放不再请求合成（计数 0 增量） |
| 手势解锁 | 未解锁时 play → 先播静音再播正文；已解锁只播一次 |
| 超时保护 | `canplaythrough` 不触发（推进 3s）→ 报错且不卡在 loading |
| 播放失败 | Audio.play() reject → error 态 + 可重试 |
| 卸载清理 | unmount → revokeObjectURL 调用数 == 创建的 Blob 数 |
| 切题停播 | 播放中调用 stop → currentTime 归零、状态 idle |

## 验收

| 命令 | 期望 |
| --- | --- |
| `pnpm -C apps/web test --run` | 全绿 |
| 真机（T10） | 点"朗读题目"能听到中文播报（edge-tts 真合成） |

## 不做

- 不做播放列表/连续自动播下一题（面试场景由用户控制）；不做音量条；不做字幕同步高亮。

