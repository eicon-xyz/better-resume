"""Process-local counters for the resilience seam (D17: no Prometheus, honest numbers)."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class ResilienceMetrics:
    """Counters plus two gauges; the event loop makes plain increments safe."""

    singleflight_leader: int = 0
    singleflight_follower: int = 0
    singleflight_replay: int = 0
    singleflight_error: int = 0
    singleflight_direct: int = 0
    singleflight_abandoned: int = 0
    breaker_opened: int = 0
    breaker_rejected: int = 0
    overflow_rejected: int = 0
    timeouts: int = 0
    rate_limited: int = 0
    in_flight: int = 0
    queued: int = 0
    peak_in_flight: int = 0

    def snapshot(self) -> dict[str, int]:
        return asdict(self)
