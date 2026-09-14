"""Pick the transcription adapter from settings (xunfei in real runs, scripted otherwise)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from ..settings import Settings
from .adapters import (
    MediaConfigError,
    ParaformerRealtimeAdapter,
    QwenAsrFlashAdapter,
    ScriptedTranscriptionChannel,
    XunfeiAstAdapter,
    XunfeiCredentials,
    derive_realtime_ws_url,
)
from .models import TranscriptEvent
from .protocols import TranscriptionChannel

EventSink = Callable[[TranscriptEvent], Awaitable[None] | None]


def build_transcription_channel(settings: Settings, *, on_event: EventSink) -> TranscriptionChannel:
    media = settings.media
    if media.transcription_adapter == "scripted":
        return ScriptedTranscriptionChannel(on_event=on_event)
    if media.transcription_adapter == "xunfei":
        credentials = XunfeiCredentials(
            app_id=settings.xunfei_app_id,
            access_key_id=settings.xunfei_access_key_id,
            access_key_secret=settings.xunfei_access_key_secret,
        ).require()
        return XunfeiAstAdapter(
            credentials=credentials,
            on_event=on_event,
            ws_url=media.xunfei_ws_url,
        )
    if media.transcription_adapter == "qwen-asr":
        # Batch model: buffer while the button is held, one request on release.
        return QwenAsrFlashAdapter(
            api_key=settings.dashscope_api_key,
            endpoint=media.asr_url,
            model=media.asr_model,
            timeout_seconds=media.asr_timeout_seconds,
            on_event=on_event,
        )
    if media.transcription_adapter == "paraformer-rt":
        # Realtime channel: partials stream while the button is held, so the M4
        # sentence pool runs for real (the batch adapter answers once per release).
        ws_url = media.asr_ws_url or derive_realtime_ws_url(media.asr_url)
        return ParaformerRealtimeAdapter(
            api_key=settings.dashscope_api_key,
            ws_url=ws_url,
            model=media.asr_realtime_model,
            timeout_seconds=media.asr_timeout_seconds,
            on_event=on_event,
        )
    raise MediaConfigError(f"unknown transcription adapter: {media.transcription_adapter}")
