"""Per-stage resilience budgets, derived from settings (§4.1.4 table + one chat row)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .models import Stage

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..settings import Settings


@dataclass(frozen=True, slots=True)
class StagePolicy:
    stage: Stage
    timeout: float
    max_concurrency: int
    queue_wait: float
    replay_ttl: float
    negative_ttl: float
    is_stream: bool = False
    allow_stream_replay: bool = False


@dataclass(frozen=True, slots=True)
class StagePolicies:
    chat: StagePolicy
    extraction: StagePolicy
    evaluation: StagePolicy
    followup: StagePolicy

    def for_stage(self, stage: Stage) -> StagePolicy:
        return {
            Stage.CHAT: self.chat,
            Stage.EXTRACTION: self.extraction,
            Stage.EVALUATION: self.evaluation,
            Stage.FOLLOWUP: self.followup,
        }[stage]

    @classmethod
    def from_settings(cls, settings: Settings) -> StagePolicies:
        resilience = settings.resilience

        def build(
            stage: Stage,
            *,
            timeout: float,
            max_concurrency: int,
            replay_ttl: float,
            negative_ttl: float,
            is_stream: bool = False,
        ) -> StagePolicy:
            return StagePolicy(
                stage=stage,
                timeout=timeout,
                max_concurrency=max_concurrency,
                queue_wait=resilience.queue_wait_seconds,
                replay_ttl=replay_ttl,
                negative_ttl=negative_ttl,
                is_stream=is_stream,
            )

        return cls(
            chat=build(
                Stage.CHAT,
                timeout=resilience.chat_timeout_seconds,
                max_concurrency=resilience.chat_max_concurrency,
                replay_ttl=resilience.chat_replay_seconds,
                # Chat is a conversation: a retry must reach the vendor again, so no
                # negative cache either (M1 semantics: the user sees the failure and retries).
                negative_ttl=0.0,
                is_stream=True,
            ),
            extraction=build(
                Stage.EXTRACTION,
                timeout=resilience.extraction_timeout_seconds,
                max_concurrency=resilience.extraction_max_concurrency,
                replay_ttl=resilience.extraction_replay_seconds,
                negative_ttl=resilience.negative_cache_seconds,
            ),
            evaluation=build(
                Stage.EVALUATION,
                timeout=resilience.evaluation_timeout_seconds,
                max_concurrency=resilience.evaluation_max_concurrency,
                replay_ttl=resilience.evaluation_replay_seconds,
                negative_ttl=resilience.negative_cache_seconds,
            ),
            followup=build(
                Stage.FOLLOWUP,
                timeout=resilience.followup_timeout_seconds,
                max_concurrency=resilience.followup_max_concurrency,
                replay_ttl=resilience.followup_replay_seconds,
                negative_ttl=resilience.negative_cache_seconds,
            ),
        )
