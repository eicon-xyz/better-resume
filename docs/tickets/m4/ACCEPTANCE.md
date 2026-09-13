# M4 验收证据（media：转写 WS + TTS 播报 → 语音答题全流程）

> 日期：2026-09-14 ｜ 分支：m4/media ｜ 票据：docs/tickets/m4/（T1–T9、T11 完成；T10 待凭据）
> PR：https://github.com/eicon-xyz/better-resume/pull/4（双 job success，run 34763326877）
> 合并：merge commit f3888a4；合并后 main CI run 34763418705 **双 job success**。
> 验收口径（§12.4 原文）：**语音答题全流程**。

## 1. 结论（先说清楚证据的边界）

| 项 | 结果 |
| --- | --- |
| §12.4 验收 | ✅ **契约级 + 组件级**全链路：音频帧 → 句池归并 → 三级文本 → 输入框 → 提交；题目朗读 → 真 edge-tts mp3 |
| ⚠️ 真机讯飞 AST | **未验证（缺凭据）**：本机没有 appId/accessKeyId/accessKeySecret，协议实现只有本地假 WS 服务端的契约测试，见 §6 |
| ⚠️ 真实浏览器人工验证 | **未做**：CI 无麦克风/扬声器；组件测试用注入的 capture/socket 工厂，见 §6 |
| 后端测试 | **473 passed**（M3 415 → +58），media 相关 40 例（句池 22 / 适配器 10 / TTS 8） |
| 前端测试 | **152 passed**（M3 115 → +37） |
| 本地 CI 矩阵 | **12/12 全绿**（与 workflow 同命令，§4） |
| 迁移 | 无 schema 变更（alembic check 干净）；新增 HTTP 端点 POST/GET /api/v1/media/tts、POST /api/v1/auth/ws-ticket 已进契约 |
| 问题台账 | docs/tickets/m4/PROBLEMS.md：P0–P12 |

## 2. 句池归并（D16 亮点③）的算法证据

media/assembler.py 的分支与对应用例（tests/media/test_assembler.py，22 例）：

| 协议分支 | 输入 | 输出（display / committed / live） |
| --- | --- | --- |
| pgs=apd 追加 | 你好 + apd 世界 | 你好世界 / 空 / 你好世界 |
| pgs=rpl 删区间 | 你好世界 + rpl rg=[2,4] 地球 | 你好地球 |
| rpl 越界 | 短 + rpl rg=[0,999] | 很长的一段文本（clamp，不抛异常） |
| 无 pgs + 重叠度/演化 | bg0-1000 我负责了订单 → bg100-1100 我负责了订单写入链路 | 同一段被改写（不新增段） |
| 无 pgs 重叠低 | 两段不同时间、不同文本 | 顺序拼接成两段 |
| 尾缀合并 | 今天天气 + apd 天气不错 | 今天天气不错（**单字重叠不合并**，见 PROBLEMS P2） |
| final 提交 | final 包 | committed 增加、live 清空 |
| 乱序到达 | seg 2 先于 seg 1 | 按 seg_id 有序重建 |

## 3. media 冒烟（uv run python scripts/media_smoke.py --scripted，真实运行输出）

    adapter setting: scripted
    == transcription (scripted adapter, same seam as the WS endpoint) ==
      event: replace  '我负责'
      event: replace  '我负责了订单写入链路的重构'
      event: archive  '我负责了订单写入链路的重构。'
      event: final    '我负责了订单写入链路的重构。'
      sequence: ['replace', 'replace', 'archive', 'final']
      final   : '我负责了订单写入链路的重构。'
    == tts (real edge-tts through the cache) ==
      tts_synthesized  bytes=25200 digest=5f6e3114a66f voice=zh-CN-XiaoxiaoNeural
      voice : zh-CN-XiaoxiaoNeural
      bytes : 25200
      header: MPEG 帧同步字（ff f3），文件可播放
      file  : data/tts/5f6e3114a66f....mp3
    result: ok

TTS 是真合成（edge-tts 在线服务），不是预置音频；同一文本第二次请求命中缓存不再调供应商（tests/test_media_tts_api.py）。

## 4. 本地 CI 矩阵（12/12）

    PASS 01 uv sync --frozen        PASS 07 openapi --check
    PASS 02 ruff check              PASS 08 pnpm install --frozen-lockfile
    PASS 03 ruff format --check     PASS 09 web lint
    PASS 04 pytest (473)            PASS 10 web typecheck
    PASS 05 alembic upgrade head    PASS 11 web test (152)
    PASS 06 alembic check           PASS 12 web check:api


## 5. 全链路是怎么被证明的

| 环节 | 证据 |
| --- | --- |
| WS 一次票据 | tests/test_ws_ticket.py：401 / 用后即焚 / 过期 / Redis Lua 原子 GET+DEL（Redis 6.0 无 GETDEL） |
| WS 端点 | tests/test_media_ws.py：无票 4401、复用 4401、并发第二路 4409、音频帧→事件、stop 帧→final、断开释放通道 |
| 音频 → PCM | src/audio/pcm.test.ts：48k→16k（1kHz 过零计数不变）、PCM16 不溢出、640 样本切片、尾部零填充 |
| WS 客户端 | src/audio/transcriptionSocket.test.ts：连接前 24 帧队列 + 丢帧计数、内容去重、有界重连、stop 后不再发送 |
| 麦克风采集 | src/audio/capture.test.ts：采集→切片、stop 时 flush 并释放 track、权限拒绝上抛 |
| 三级文本消费 | src/audio/transcriptStore.test.ts：replace/archive/final 语义、mergeTranscript 不覆盖手写文本、两个消费方共用一份 store |
| 播放器 | src/audio/player.test.ts：单例、缓存命中不重复合成、手势解锁一次、canplaythrough 3s 超时、dispose revoke 全部 Blob |
| 页面接线 | src/pages/VoiceWiring.test.tsx（8 例）：store→输入框→提交带完整文本；提交失败保留文本；朗读触发合成；麦克风错误提示 |
| 后端 TTS | tests/media/test_tts.py + tests/test_media_tts_api.py（14 例）：缓存键、并发单飞、503/504、原子写、路径穿越 404 |

## 6. 未验证项（明确列出，不含糊）

1. **讯飞 AST 真机**：无凭据 → 签名是否被供应商接受、真实 PCM 的识别效果、cn.st 真实报文形状都未验证。
   复跑方式：设好 BR_XUNFEI_APP_ID / BR_XUNFEI_ACCESS_KEY_ID / BR_XUNFEI_ACCESS_KEY_SECRET 后
   `uv run python scripts/media_smoke.py`（不带 --scripted）。
2. **真实浏览器人工验证**：麦克风权限弹窗、AudioWorklet 真实路径、autoplay 手势解锁、Vite 代理 WS 升级。
   开发代理已开 ws: true（PROBLEMS P9），但需要人点一次才能确认。
3. **AudioWorklet 分支**：单测只覆盖 ScriptProcessor 回退分支（jsdom 无 AudioWorklet）；worklet 源码内联为 Blob URL，未在真浏览器跑过。
4. **移动端 Safari**：未测（已知限制：AudioWorklet 与 autoplay 策略更严）。

## 7. 与提案的偏差

1. **TranscriptionChannel 协议扩展了 wait()**（M0 草图只有 start/feed/stop）：端点需要"通道自己结束或失败"的信号，见 PROBLEMS P5。
2. **WS 停止语义用显式 stop 帧**：客户端释放按钮发 {"type":"stop"} → 服务端先 stop 通道（产出 archive/final）→ flush → 关闭；直接断开收不到 final（PROBLEMS P6）。
3. **事件去重按内容 key**，不是 revision：后端 TranscriptEvent 目前不带 revision（assembler 的 revision 留在服务端），前端用 kind|seg_id|text 去重。
4. **TTS 走 M3 韧性链且新增 Stage.TTS**（预算独立：20s / 8 并发 / 300s 回放），并发同文本只真合成一次。
5. **音频 GET 需要登录**：同源 audio 元素会自动带 cookie；未知/非 hex digest 一律 404（防路径穿越）。
6. **合成落盘是原子写**（tmp + os.replace），并发同文本由缓存 + 单飞保证只写一次。
7. **前端 answer 状态上移到页面**：AnswerComposer 改成受控组件，才能在"转写到达"与"用户手写"之间做合并决策（T6 规则）。
8. **未做**：草稿板（D09 砍）、AEC/降噪自研、离线 ASR、多路并发转写（D15 单通道）。

## 8. 复跑方式

    # 后端（本机原生库）
    export BR_DATABASE_URL='postgresql+asyncpg://better_resume:better_resume@127.0.0.1:5433/better_resume'
    export BR_REDIS_URL='redis://127.0.0.1:6379/0'
    cd apps/api && uv run pytest -q                     # 473 passed
    uv run python scripts/media_smoke.py --scripted     # §3 的证据（含真 edge-tts 合成）

    # 前端
    pnpm -C apps/web test --run                          # 152 passed

