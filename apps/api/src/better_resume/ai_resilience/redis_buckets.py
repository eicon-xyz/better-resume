"""Shared (cross-replica) bucket store on Redis — one atomic Lua round trip (P7 / D19).

Why a Lua script: read-modify-write on a bucket key cannot be two round trips, or two
replicas both see the last token. The script's arithmetic mirrors the in-process
`TokenBucket`: `take_lua_math` below is that mirror as executable Python, and
`tests/ai_resilience/test_ratelimit_equivalence.py` pins the two together — same verdicts,
same refill, bit for bit. Change the arithmetic on one side and you must change it on the
other, or that test goes red. Two differences Redis forces:

* the script stringifies its reply (`tostring`), so `take` converts it back to `int`/`float`;
* the bucket key expires on its own (TTL ≈ 3 × full refill, floor 60s) — that replaces the
  in-process `max_identities` lazy eviction.

The time base is passed in from the app (`WallClock.now_ms()`), not read from
`redis.call('TIME')`, so refill is deterministic under an injected clock.
"""

from __future__ import annotations

import math

from ..redis_client import RedisSource, redis_client
from .clock import SystemWallClock, WallClock
from .ratelimit import BucketScope

#: KEYS[1] = bucket key; ARGV = now_ms, rate_per_second, capacity, ttl_ms.
#:
#: This is the Redis-side mirror of `TokenBucket.take`. `take_lua_math` below is the same
#: arithmetic as executable Python, and `tests/ai_resilience/test_ratelimit_equivalence.py`
#: pins the two together. Keep the operation order exactly as written here
#: (`elapsed / 1000 * rate`, never `elapsed * rate / 1000` — the two round differently):
#: change the arithmetic on either side and you must change it on the other, or that test
#: goes red.
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


def take_lua_math(
    *,
    tokens: float | None,
    ts_ms: float | None,
    now_ms: float,
    rate: float,
    capacity: float,
) -> tuple[bool, float, int, float, float]:
    """`_TAKE_LUA`'s arithmetic as executable Python — the mirror *is* the contract.

    Every line mirrors the script, in the script's own operation order (`elapsed / 1000 *
    rate`, never `elapsed * rate / 1000`: the two round differently, and
    `tests/ai_resilience/test_ratelimit_equivalence.py` pins the order with a bit-exact
    comparison). `tokens=None` is the script's "no hash yet" branch.

    Returns the script's reply plus the state it writes back:
    `(allowed, retry_after, remaining, tokens_after, ts_after)`. The first three are what
    `return { allowed, tostring(retry), tostring(math.floor(tokens)) }` sends to the
    client; the last two are what the `HSET` stores, and they exist so a caller can drive
    a whole sequence through this one definition instead of copying the state update.

    `math.floor` versus the in-process `int(self._tokens)`: the two agree while tokens
    stay non-negative, which they always are here (elapsed is clamped at 0, rate > 0).
    """
    if tokens is None:
        tokens = capacity
        ts_ms = now_ms
    elapsed = now_ms - ts_ms
    if elapsed < 0:
        elapsed = 0
    tokens = tokens + elapsed / 1000 * rate
    if tokens > capacity:
        tokens = capacity
    if tokens >= 1:
        tokens = tokens - 1
        allowed, retry = True, 0.0
    else:
        allowed, retry = False, (1 - tokens) / rate
    return allowed, retry, math.floor(tokens), tokens, now_ms


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
