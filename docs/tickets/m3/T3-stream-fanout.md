# M3-T3 — 流式单飞广播（聊天流同 key 并发只调一次上游）

- blocking：M3-T2
- 纪律：先写失败测试（红），再实现（绿）

## 目标

run() 的返回类型可能是 AsyncIterator（聊天流）。**当前 M1/M2 的直通实现下，
两个并发同 key 的聊天请求会各自打开一条上游流**；如果只是把值单飞套上去，
第二个调用者会拿到**同一个 async generator 对象**——第二个消费者直接 RuntimeError。
本票给出正确语义：**单生产者 + 多消费者游标 + 迟到订阅从头回放 + 全部离开才取消**。

## 交付物

- ai_resilience/stream.py：
  - StreamBroadcast：frames: list、error: BaseException | None、done: bool、
    每消费者游标；subscribe() -> AsyncIterator[T]；publish(frame)；finish(error)
  - 生产者是**独立 task**（不挂在任何消费者上）：leader 或 follower 提前退出不影响其他消费者
  - 背压：缓冲帧数超过 stream_buffer_frames 时生产者 await（聊天流上游比 SSE 写快，
    暂停拉取是正确的背压，而不是丢帧）
  - 消费者引用计数归零 → 取消生产者 task，清理登记（避免"客户端全断了，模型还在跑"）
  - 迟到订阅者（流进行中加入）从头回放已有帧 → 内容与 leader 逐字节一致
  - 生产者异常：记录后唤醒所有消费者，各自在游标处抛出同一异常（不是挂死）
- singleflight.py 扩展：execute() 检测结果为 AsyncIterator → 走 StreamBroadcast
  分支（同一 key 的在飞流共享；**不**做完成后回放，policy allow_stream_replay=False）
- 测试：tests/ai_resilience/test_stream_fanout.py（≥10 例）

## 测试

| 用例 | 断言 |
| --- | --- |
| 3 个并发消费者同 key | 上游被订阅 **1** 次；三方帧序列完全一致（逐帧比对） |
| 迟到消费者（第 3 帧后加入） | 从第 1 帧开始收到完整序列 |
| leader 提前 break | 生产者不被打断；其他消费者继续收到剩余帧并正常结束 |
| 全部消费者退出 | 生产者被取消（假时钟下断言 task 状态），登记被清理 |
| 上游中途抛错 | 每个消费者都在同一位置收到同一异常；无挂起用例（用 wait_for 兜底） |
| 背压 | 消费者慢于生产者时缓冲不超过上限（断言生产者在 max_buffered 处阻塞） |
| 非流式调用者混入同 key | 明确报错（类型冲突），不静默返回半个流 |
| allow_stream_replay=False | 流结束后同 key 再订阅 → 起新上游流（不是回放旧的） |

## 验收

| 命令 | 期望 |
| --- | --- |
| uv run pytest -q tests/ai_resilience/test_stream_fanout.py | 全绿 |
| 端到端（T8 复验） | 两个并发 POST /sessions/{id}/stream 同 content → 上游 stream() 调用计数 1，两路 SSE 文本一致 |

## 不做

- 不做跨进程流广播（M6）；不做断线续传/重连（M1 已明确不做）；不做帧压缩/落盘回放（M6）。

