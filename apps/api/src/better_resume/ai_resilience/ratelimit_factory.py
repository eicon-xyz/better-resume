"""Assembly: which bucket store each bucket gets (P7 / D19).

Kept out of `ratelimit.py` on purpose — the policy module must not know about Redis
(`redis_buckets` imports `BucketScope` from it, so the dependency only ever points here).
"""

from __future__ import annotations

from ..redis_client import RedisTopology
from ..settings import Settings
from .clock import Clock, SystemClock, SystemWallClock, WallClock
from .degraded import DegradingBucketStore
from .metrics import ResilienceMetrics
from .ratelimit import Bucket, InProcessBucketStore, RateLimiter
from .redis_buckets import RedisBucketStore


def build_rate_limiter(
    settings: Settings,
    *,
    clock: Clock | None = None,
    wall_clock: WallClock | None = None,
    metrics: ResilienceMetrics | None = None,
) -> RateLimiter:
    """Wire the limiter the settings ask for.

    backend=memory: every bucket is per-process (pre-P7 behaviour).
    backend=redis: the buckets in `shared_buckets` share one quota through Redis, degrade
    to the in-process bucket when Redis is unavailable, and report `scope` accordingly.
    """
    limits = settings.rate_limit
    clock = clock or SystemClock()
    metrics = metrics or ResilienceMetrics()
    fallback = InProcessBucketStore(clock=clock)

    if limits.backend != "redis":
        return RateLimiter(limits, clock=clock, metrics=metrics, store=fallback)

    shared = limits.shared_bucket_names
    degrading = DegradingBucketStore(
        RedisBucketStore(
            RedisTopology.from_settings(settings),
            clock=wall_clock or SystemWallClock(),
            socket_timeout=limits.redis_socket_timeout_ms / 1000,
        ),
        fallback,
        cooldown_seconds=limits.degraded_cooldown_seconds,
        clock=clock,
        metrics=metrics,
    )
    stores = {bucket: (degrading if bucket.value in shared else fallback) for bucket in Bucket}
    return RateLimiter(limits, clock=clock, metrics=metrics, store=fallback, stores=stores)
