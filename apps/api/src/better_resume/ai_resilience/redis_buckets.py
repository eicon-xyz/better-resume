"""Shared (cross-replica) bucket store on Redis — one atomic Lua round trip (P7 / D19).

Why a Lua script: read-modify-write on a bucket key cannot be two round trips, or two
replicas both see the last token. The script keeps the *same* arithmetic as the in-process
`TokenBucket` (so the degraded path behaves like the shared one), with two differences
that Redis forces:

* numbers come back from Lua as integers, so the fractional replies are returned as strings;
* the bucket key expires on its own (TTL ≈ 3 × full refill, floor 60s) — that replaces the
  in-process `max_identities` lazy eviction.

The time base is passed in from the app (`WallClock.now_ms()`), not read from
`redis.call('TIME')`, so refill is deterministic under an injected clock.
"""

from __future__ import annotations

from ..redis_client import RedisSource, redis_client
from .clock import SystemWallClock, WallClock
from .ratelimit import BucketScope

#: KEYS[1] = bucket key; ARGV = now_ms, rate_per_second, capacity, ttl_ms.
_TAKE_LUA = """
local state = redis.call('HMGET', KEYS[1], 'tokens', 'ts')
local tokens = tonumber(state[1])
local ts = tonumber(state[2])
local now = tonumber(ARGV[1])
local rate = tonumber(ARGV[2])
local cap = tonumber(ARGV[3])
if tokens == nil then
  tokens = cap
  ts = now
end
local elapsed = now - ts
if elapsed < 0 then elapsed = 0 end
tokens = tokens + elapsed / 1000 * rate
if tokens > cap then tokens = cap end
local allowed = 0
local retry = 0
if tokens >= 1 then
  tokens = tokens - 1
  allowed = 1
else
  retry = (1 - tokens) / rate
end
redis.call('HSET', KEYS[1], 'tokens', tostring(tokens), 'ts', tostring(now))
redis.call('PEXPIRE', KEYS[1], ARGV[4])
return { allowed, tostring(retry), tostring(math.floor(tokens)) }
"""

#: Floor for the key TTL: a bucket that refills in 200ms should not expire mid-burst.
_MIN_TTL_MS = 60_000


class RedisBucketStore:
    """Buckets shared by every replica; keys are `br:rl:{bucket}|{identity}`."""

    scope = BucketScope.SHARED

    def __init__(
        self,
        redis_source: RedisSource,
        *,
        clock: WallClock | None = None,
        prefix: str = "br:rl",
        socket_timeout: float | None = None,
        min_ttl_ms: int = _MIN_TTL_MS,
    ) -> None:
        self.clock = clock or SystemWallClock()
        self._prefix = prefix
        self._min_ttl_ms = max(1, min_ttl_ms)
        self._client = redis_client(
            redis_source, decode_responses=True, socket_timeout=socket_timeout
        )

    @property
    def tracked(self) -> int:
        """Redis owns the registry; there is no local dict to report."""
        return 0

    def redis_key(self, key: str) -> str:
        return f"{self._prefix}:{key}"

    async def take(self, key: str, *, rate: float, capacity: float) -> tuple[bool, float, int]:
        full_refill_ms = int(capacity / max(rate, 1e-9) * 1000)
        ttl_ms = max(self._min_ttl_ms, full_refill_ms * 3)
        allowed, retry, remaining = await self._client.eval(
            _TAKE_LUA,
            1,
            self.redis_key(key),
            self.clock.now_ms(),
            repr(rate),
            repr(capacity),
            ttl_ms,
        )
        return bool(int(allowed)), float(retry), int(remaining)

    async def ping(self) -> bool:
        return bool(await self._client.ping())

    async def pttl(self, key: str) -> int:
        return int(await self._client.pttl(self.redis_key(key)))

    async def aclose(self) -> None:
        await self._client.aclose()
