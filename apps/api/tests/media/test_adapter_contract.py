"""TranscriptionChannel 协议契约：实现 Protocol 不等于满足契约（P11）。

三条契约，每条都配一个故意违规的假适配器，证明套件会把它判红：

1. `wait()` 必须阻塞到 `stop()`——提前返回等于告诉转写 WebSocket 这一轮已经结束，
   而句子池还在等供应商的尾巴（P20 的批量适配器就是这么错的）。
2. WS 类适配器跑完一轮后必须显式 `close(1000)`——把关闭码留给库默认值，一次干净结束
   和一次异常断开在两端都分不出来（P21）。
3. 真实连接必须自己传 `open_timeout` / `close_timeout` / `proxy`，不吃 `websockets`
   默认值——默认 `close_timeout` 是 10 s，供应商拖关闭握手时「松手→final」就是 10 s（P24）。

契约 1 的主体是全部三个可驱动通道：scripted、qwen-asr、paraformer-rt；契约 2 的主体是
paraformer-rt（经它自己的 `connect=` 缝用假供应商驱动）；契约 3 的主体是真实开连接函数
`open_connection`。xunfei AST 跳过：它的接收循环直接绑定 `websockets.connect`，没有注入缝，
跑契约需要真实供应商（凭据 + 网络），本套件不允许有这个前提。
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
import websockets

from better_resume.ai_resilience import wait_until
from better_resume.media import (
    ChannelCtx,
    QwenAsrFlashAdapter,
    ScriptedTranscriptionChannel,
    TranscriptEvent,
)
from better_resume.media.adapters.paraformer_rt import open_connection
from tests.media.test_paraformer_rt import (
    SAMPLE_PCM,
    FakeVendor,
    build_adapter,
    result_generated,
)

from ..support import settle

WS_URL = "wss://example.invalid/api-ws/v1/inference"
ASR_URL = "https://example.invalid/api/v1/services/aigc/multimodal-generation/generation"

#: 库默认值在模块导入时取，早于任何 monkeypatch：断言的是「我们没吃这个默认值」。
_CONNECT_PARAMETERS = inspect.signature(websockets.connect).parameters
_LIBRARY_CLOSE_TIMEOUT = (
    _CONNECT_PARAMETERS["close_timeout"].default if "close_timeout" in _CONNECT_PARAMETERS else None
)


class ConnectSpy:
    """`websockets.connect` 的替身：只记录开连接方传了什么（系统边界，不是内部模块）。"""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, url: str, **kwargs: Any) -> Any:
        self.calls.append({"url": url, **kwargs})
        return object()


async def _nothing(_channel: Any) -> None:
    return None


async def assert_wait_blocks_until_stop(
    channel: Any, drive: Callable[[Any], Awaitable[None]] = _nothing
) -> None:
    """契约 1：`wait()` 在 `stop()` 之前不得返回，`stop()` 之后必须返回。"""
    await channel.start(ChannelCtx(session_id="adapter-contract"))
    await drive(channel)
    watcher = asyncio.create_task(channel.wait())
    await settle(5)  # 让 wait() 走到第一个 await：提前返回的 fake 这时已经做完
    assert not watcher.done(), (
        "wait() returned before stop(): the transcription WebSocket would close the client "
        "socket while the vendor tail is still coming (P20)"
    )
    await channel.stop()
    await asyncio.wait_for(watcher, timeout=1)


async def assert_success_closes_with_1000(
    channel: Any, transport: Any, drive: Callable[[Any], Awaitable[None]] = _nothing
) -> None:
    """契约 2：成功跑完一轮后，供应商 socket 必须以显式 1000 关闭。"""
    await channel.start(ChannelCtx(session_id="adapter-contract"))
    await drive(channel)
    await channel.stop()
    await channel.wait()
    code = getattr(transport, "closed_with", "NO CLOSE SEEN")
    assert code == 1000, (
        f"a successful WS run must close the vendor socket with an explicit 1000 (got {code!r}): "
        "leaving the code to the library default hides a stalled close from both ends (P21)"
    )


async def assert_connect_params_explicit(
    opener: Callable[..., Awaitable[Any]], spy: ConnectSpy
) -> None:
    """契约 3：开连接的一方自己传时限与代理，不吃库默认值。"""
    await opener(WS_URL, {"Authorization": "Bearer contract"}, 5.0)
    assert len(spy.calls) == 1, f"expected one websockets.connect call, got {len(spy.calls)}"
    kwargs = spy.calls[0]
    assert kwargs.get("open_timeout") == 5.0, (
        f"open_timeout must be the caller value, got {kwargs.get('open_timeout')!r}"
    )
    assert kwargs.get("close_timeout") not in (None, _LIBRARY_CLOSE_TIMEOUT), (
        "close_timeout must be explicit and tighter than the websockets default "
        f"({_LIBRARY_CLOSE_TIMEOUT}), got {kwargs.get('close_timeout')!r}: the vendor stalls "
        "the close handshake and the transcript is already complete (P24)"
    )
    assert "proxy" in kwargs and kwargs["proxy"] is None, (
        "proxy must be explicit (None) instead of letting the library parse the environment: "
        "this machine exports a malformed NO_PROXY (P12)"
    )
    headers = kwargs.get("additional_headers") or kwargs.get("extra_headers")
    assert headers == {"Authorization": "Bearer contract"}, (
        f"the handshake headers must reach the connection unchanged, got {headers!r}"
    )


class EarlyWaitChannel:
    """坏 fake：`wait()` 立刻返回。契约 1 必须判红。"""

    async def start(self, ctx: ChannelCtx) -> None: ...

    async def feed(self, pcm: bytes) -> None: ...

    async def stop(self) -> None: ...

    async def wait(self) -> None: ...


class _DefaultCloseTransport:
    """坏 fake 的 socket：关闭时不吃显式码，等于把关闭码留给库默认值。"""

    def __init__(self) -> None:
        self.closed_with: int | None = None

    async def close(self, code: int | None = None) -> None:
        self.closed_with = code


class SilentCloseChannel:
    """坏 fake：跑完一轮但 socket 不带 1000 关闭。契约 2 必须判红。"""

    def __init__(self) -> None:
        self.transport = _DefaultCloseTransport()
        self._finished = asyncio.Event()

    async def start(self, ctx: ChannelCtx) -> None:
        self._finished.clear()

    async def feed(self, pcm: bytes) -> None: ...

    async def stop(self) -> None:
        await self.transport.close()
        self._finished.set()

    async def wait(self) -> None:
        await self._finished.wait()


async def _open_with_library_defaults(
    url: str, headers: dict[str, str], open_timeout: float
) -> Any:
    """坏 fake 的开连接方：只传头，时限与代理全吃库默认值。契约 3 必须判红。"""
    import websockets as ws

    return await ws.connect(url, additional_headers=headers)


async def _press(channel: Any, vendor: FakeVendor) -> None:
    """把音频喂进去，并等到它真的流到供应商（不靠固定 sleep 断言时序）。"""
    await channel.feed(SAMPLE_PCM)
    await wait_until(
        lambda: any(isinstance(frame, bytes) for frame in vendor.client_frames),
        timeout=1.0,
        description="the channel to stream the audio it was fed",
    )


def _success_frames() -> list[str]:
    return [result_generated("契约文本。", end=True)]


# ---- 契约 1：wait() 阻塞到 stop() -------------------------------------------------


async def test_scripted_channel_wait_blocks_until_stop() -> None:
    events: list[TranscriptEvent] = []
    await assert_wait_blocks_until_stop(ScriptedTranscriptionChannel(on_event=events.append))


async def test_batch_asr_wait_blocks_until_stop() -> None:
    channel = QwenAsrFlashAdapter(
        api_key="sk-contract", endpoint=ASR_URL, on_event=lambda _event: None
    )
    await assert_wait_blocks_until_stop(channel)


async def test_realtime_asr_wait_blocks_until_stop() -> None:
    adapter, _events, vendor = build_adapter(_success_frames())
    await assert_wait_blocks_until_stop(adapter, lambda channel: _press(channel, vendor))


async def test_contract_one_reddens_a_channel_that_returns_from_wait_early() -> None:
    with pytest.raises(AssertionError, match=r"wait\(\) returned before stop"):
        await assert_wait_blocks_until_stop(EarlyWaitChannel())


# ---- 契约 2：成功路径显式 close(1000) ------------------------------------------


async def test_realtime_asr_closes_the_vendor_socket_with_1000() -> None:
    adapter, _events, vendor = build_adapter(_success_frames())
    await assert_success_closes_with_1000(adapter, vendor, lambda channel: _press(channel, vendor))


async def test_contract_two_reddens_a_socket_closed_with_the_library_default() -> None:
    channel = SilentCloseChannel()
    with pytest.raises(AssertionError, match="explicit 1000"):
        await assert_success_closes_with_1000(channel, channel.transport)


# ---- 契约 3：连接参数显式 ------------------------------------------------------


async def test_real_ws_opener_passes_explicit_connection_params(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spy = ConnectSpy()
    monkeypatch.setattr(websockets, "connect", spy)
    await assert_connect_params_explicit(open_connection, spy)


async def test_contract_three_reddens_an_opener_using_library_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spy = ConnectSpy()
    monkeypatch.setattr(websockets, "connect", spy)
    with pytest.raises(AssertionError, match="open_timeout"):
        await assert_connect_params_explicit(_open_with_library_defaults, spy)
