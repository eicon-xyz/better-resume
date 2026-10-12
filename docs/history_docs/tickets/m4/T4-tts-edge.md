# M4-T4 — TTS：EdgeTtsAdapter + 缓存 + 端点

- blocking：M3
- 纪律：先写失败测试（红），再实现（绿）；**供应商调用是系统边界，测试用假子进程/假 HTTP**

## 目标

`TtsSynthesizer` 真实现：文本 → mp3 字节 → 磁盘缓存 `data/tts/{sha256(text|voice)}.mp3` → HTTP 返回；
失败明确降级（不静默返回空音频）。

## 交付物

- `media/adapters/edge_tts.py`：`EdgeTtsSynthesizer`（调 `edge-tts` CLI 或 python API，
  默认音色 `zh-CN-XiaoxiaoNeural`，语速可配；超时用注入时钟；失败 → `AiUnavailable`）
- `media/tts_cache.py`：内容寻址缓存（sha256 → 路径；命中直接返回；并发同 key 只合成一次
  ——**复用 M3 的单飞**，这是跨里程碑复用而不是重写）
- `http/media.py`：`POST /api/v1/media/tts`（需登录，body `{text, voice?, rate?}`）→
  命中缓存返回 `{url, mime_type, cached: true}`；未命中合成后落盘并返回；
  `GET /api/v1/media/tts/{digest}.mp3` 静态读取（带 `Cache-Control`）
- 文本长度限制（≤ 500 字，超出 422）；同文本不同音色 = 不同缓存键
- 测试：`tests/media/test_edge_tts.py`、`tests/test_media_tts_api.py`（≥10 例）

## 测试

| 用例 | 断言 |
| --- | --- |
| 缓存键 | 同文本同音色 → 同 digest；换音色/语速 → 不同 digest |
| 命中缓存 | 第二次请求不再调供应商（计数 0 增量）且 `cached=true` |
| 并发同文本 | 两路并发 → 供应商只被调用 1 次（复用单飞） |
| 供应商失败 | 返回 503 + kind=unavailable；**不写半截文件**（临时文件 + 原子 rename） |
| 超时 | 假时钟推进 → 504 |
| 静态读取 | 不存在的 digest → 404；存在 → 200 + 正确 content-type + 缓存头 |
| 过长文本 | >500 字 → 422 |

## 验收

| 命令 | 期望 |
| --- | --- |
| `uv run pytest -q tests/media/test_edge_tts.py tests/test_media_tts_api.py` | 全绿 |
| 真合成（T10） | 真跑一次 edge-tts，得到可播放 mp3（记录字节数与时长） |

## 不做

- 不做长文本三模式（createTask/轮询）；不做流式边合成边播（短句场景收益低）；
  不做多音色管理后台。

