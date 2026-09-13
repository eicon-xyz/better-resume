"""M3-T1: per-stage policy derived from settings (no magic numbers at call sites)."""

from __future__ import annotations

from better_resume.ai_resilience import Stage, StagePolicies
from better_resume.settings import ResilienceSettings, Settings


def test_defaults_follow_the_architecture_table() -> None:
    policies = StagePolicies.from_settings(Settings(_env_file=None))

    extraction = policies.for_stage(Stage.EXTRACTION)
    assert extraction.timeout == 60.0
    assert extraction.max_concurrency == 8

    evaluation = policies.for_stage(Stage.EVALUATION)
    assert evaluation.timeout == 20.0
    assert evaluation.max_concurrency == 30

    followup = policies.for_stage(Stage.FOLLOWUP)
    assert followup.timeout == 20.0
    assert followup.max_concurrency == 20

    chat = policies.for_stage(Stage.CHAT)
    assert chat.timeout == 180.0
    assert chat.max_concurrency == 16
    assert chat.replay_ttl == 0.0
    assert chat.is_stream is True
    assert chat.allow_stream_replay is False
    assert extraction.is_stream is False


def test_replay_ttls_are_per_stage() -> None:
    policies = StagePolicies.from_settings(Settings(_env_file=None))
    assert policies.for_stage(Stage.CHAT).replay_ttl == 0.0
    assert policies.for_stage(Stage.EVALUATION).replay_ttl == 60.0
    assert policies.for_stage(Stage.FOLLOWUP).replay_ttl == 60.0
    assert policies.for_stage(Stage.EXTRACTION).replay_ttl == 300.0
    assert policies.for_stage(Stage.EVALUATION).negative_ttl == 10.0


def test_settings_override_every_stage() -> None:
    settings = Settings(
        _env_file=None,
        resilience=ResilienceSettings(
            chat_timeout_seconds=9.0,
            evaluation_max_concurrency=2,
            evaluation_replay_seconds=1.5,
            queue_wait_seconds=0.25,
        ),
    )
    policies = StagePolicies.from_settings(settings)

    assert policies.for_stage(Stage.CHAT).timeout == 9.0
    evaluation = policies.for_stage(Stage.EVALUATION)
    assert evaluation.max_concurrency == 2
    assert evaluation.replay_ttl == 1.5
    assert evaluation.queue_wait == 0.25
    assert policies.for_stage(Stage.EXTRACTION).timeout == 60.0


def test_every_stage_has_a_policy() -> None:
    policies = StagePolicies.from_settings(Settings(_env_file=None))
    for stage in Stage:
        assert policies.for_stage(stage).stage is stage
