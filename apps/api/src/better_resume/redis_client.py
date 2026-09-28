"""取 Redis 客户端的唯一缝（P5：主挂了应用自己切到可用节点）。

为什么单独一个模块：Redis 是横跨 `identity` / `jobs` / `interview_engine` /
`ai_resilience` 的共享依赖，不属于任何单一功能模块；而 `db/` 明确是 Postgres 引擎的位置
（D03 双件套各管各的）。所以放在包根，作为「连哪个节点」这件事的唯一出口。

形态：

* 不配哨兵（本地 / CI / 单机 compose 默认）→ 就是今天的 `from_url(redis_url)`，行为一模一样；
* 配了 `BR_REDIS_SENTINELS` + `BR_REDIS_MASTER_NAME` → `Sentinel(...).master_for(master)`。
  自动切换由 redis-py 的连接池负责：连接失败/被降级时它会重新向哨兵问主并丢弃旧连接
  （`SentinelConnectionPool.get_master_address`），所以 8 个调用点不需要各自懂 failover。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlsplit

import redis.asyncio as aioredis
from redis.asyncio.sentinel import Sentinel

from .settings import Settings

#: 哨兵默认端口（redis-sentinel 的标准端口）。
_DEFAULT_SENTINEL_PORT = 26379


@dataclass(frozen=True)
class RedisTopology:
    """连接目标：单个 URL，或一组哨兵 + 要监视的主名。"""

    url: str = "redis://localhost:6379/0"
    sentinels: tuple[str, ...] = field(default_factory=tuple)
    master_name: str = ""

    @classmethod
    def from_settings(cls, settings: Settings) -> RedisTopology:
        """唯一读 `BR_REDIS_SENTINELS` / `BR_REDIS_MASTER_NAME` 的地方。"""
        sentinels = tuple(
            entry.strip() for entry in settings.redis_sentinels.split(",") if entry.strip()
        )
        return cls(
            url=settings.redis_url,
            sentinels=sentinels,
            master_name=settings.redis_master_name.strip(),
        )

    @property
    def uses_sentinel(self) -> bool:
        return bool(self.sentinels and self.master_name)


#: 调用点可以传裸 URL（测试/单实例）或拓扑对象（生产装配）。
RedisSource = str | RedisTopology


def redis_client(
    source: RedisSource,
    *,
    decode_responses: bool = True,
    socket_timeout: float | None = None,
) -> aioredis.Redis:
    """按拓扑取一个客户端；调用方只拿到 `redis.asyncio.Redis`，不感知端点。"""
    topology = source if isinstance(source, RedisTopology) else RedisTopology(url=source)
    kwargs = _connection_kwargs(decode_responses, socket_timeout)
    if not topology.uses_sentinel:
        return aioredis.from_url(topology.url, **kwargs)
    # master_for 的连接池（SentinelConnectionPool）在重连时重新向哨兵问主，主换了就自动改指向；
    # 显式传一遍连接参数，免得依赖 redis-py 的「ctor kwargs 会被 master_for 继承」这条隐含约定。
    sentinel = Sentinel(
        [_sentinel_address(entry) for entry in topology.sentinels],
        **kwargs,
    )
    return sentinel.master_for(topology.master_name, **kwargs)


def _sentinel_address(entry: str) -> tuple[str, int]:
    """`redis://host:26379` / `host:26379` / `host`（默认端口）→ (host, port)。"""
    raw = entry.strip()
    if not raw:
        raise ValueError("redis sentinel address is empty; check BR_REDIS_SENTINELS")
    if "://" in raw:
        parts = urlsplit(raw)
        if not parts.hostname:
            raise ValueError(f"redis sentinel address {entry!r} has no host")
        return parts.hostname, parts.port or _DEFAULT_SENTINEL_PORT
    host, sep, port = raw.rpartition(":")
    if not sep:
        return raw, _DEFAULT_SENTINEL_PORT
    if not host or not port.isdigit():
        raise ValueError(f"redis sentinel address {entry!r} is not host:port")
    return host, int(port)


def _connection_kwargs(decode_responses: bool, socket_timeout: float | None) -> dict[str, object]:
    kwargs: dict[str, object] = {"decode_responses": decode_responses}
    if socket_timeout is not None:
        kwargs["socket_timeout"] = socket_timeout
    return kwargs
