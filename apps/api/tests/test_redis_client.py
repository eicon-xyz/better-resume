"""P5：取 Redis 客户端的唯一缝（配哨兵 / 不配哨兵）。

只 mock 系统边界：哨兵路径把 redis-py 的 `Sentinel` 换成记录入参的假对象；
单 URL 路径只检查 `from_url` 装出来的连接池参数——两者都不连真 Redis（hermetic）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import redis.asyncio as aioredis
from redis.asyncio.sentinel import SentinelConnectionPool

from better_resume import redis_client as seam
from better_resume.redis_client import RedisTopology, redis_client
from better_resume.settings import Settings

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src" / "better_resume"


class _FakeSentinel:
    """假哨兵（系统边界替身）：只记录入参，不连网。"""

    last: _FakeSentinel | None = None

    def __init__(self, sentinels: list[tuple[str, int]], **kwargs: Any) -> None:
        self.addresses = list(sentinels)
        self.connection_kwargs = kwargs
        self.master_for_calls: list[tuple[str, dict[str, Any]]] = []
        self.client = object()
        _FakeSentinel.last = self

    def master_for(self, service_name: str, **kwargs: Any) -> object:
        self.master_for_calls.append((service_name, kwargs))
        return self.client


async def test_without_sentinels_the_client_is_still_one_url() -> None:
    """没配哨兵 → 行为与今天完全一致：就是 from_url(redis_url)。"""
    client = redis_client(RedisTopology(url="redis://cache.internal:6380/2"))

    kwargs = client.connection_pool.connection_kwargs
    assert kwargs["host"] == "cache.internal"
    assert kwargs["port"] == 6380
    assert kwargs["db"] == 2
    assert kwargs["decode_responses"] is True

    await client.aclose()


async def test_sentinels_ask_sentinel_for_the_master(monkeypatch: pytest.MonkeyPatch) -> None:
    """配了哨兵 → 客户端由 Sentinel.master_for(主名) 产出，URL 不再被直接使用。"""
    monkeypatch.setattr(seam, "Sentinel", _FakeSentinel)
    topology = RedisTopology(
        url="redis://redis:6379/0",
        sentinels=("redis://sentinel-a:26379", "sentinel-b:26380"),
        master_name="br-master",
    )

    client = seam.redis_client(topology, decode_responses=True, socket_timeout=5.0)

    fake = _FakeSentinel.last
    assert fake is not None
    assert client is fake.client
    assert fake.addresses == [("sentinel-a", 26379), ("sentinel-b", 26380)]
    assert fake.connection_kwargs["decode_responses"] is True
    assert fake.master_for_calls == [
        ("br-master", {"decode_responses": True, "socket_timeout": 5.0})
    ]


def test_topology_from_settings_parses_the_comma_separated_list() -> None:
    """唯一读配置的地方：逗号分隔、容忍空格，主名原样带过去。"""
    settings = Settings(
        _env_file=None,
        redis_url="redis://redis:6379/0",
        redis_sentinels=" redis://sentinel-a:26379 , sentinel-b:26380 ,sentinel-c ",
        redis_master_name="br-master",
    )

    topology = RedisTopology.from_settings(settings)

    assert topology.url == "redis://redis:6379/0"
    assert topology.sentinels == ("redis://sentinel-a:26379", "sentinel-b:26380", "sentinel-c")
    assert topology.master_name == "br-master"
    assert topology.uses_sentinel is True


def test_topology_from_settings_without_sentinels_is_a_single_url() -> None:
    settings = Settings(_env_file=None, redis_url="redis://localhost:6379/0")

    topology = RedisTopology.from_settings(settings)

    assert topology.sentinels == ()
    assert topology.uses_sentinel is False


async def test_the_master_client_can_re_resolve_after_a_failover() -> None:
    """自动切换靠连接池：重连时它重新问哨兵要主，主换了就改指向（这里不连网，只钉住这个契约）。"""
    client = redis_client(
        RedisTopology(
            url="redis://redis:6379/0",
            sentinels=("sentinel-a:26379",),
            master_name="br-master",
        )
    )

    pool = client.connection_pool
    assert isinstance(pool, SentinelConnectionPool)
    assert pool.service_name == "br-master"
    assert pool.is_master is True

    await client.aclose()


@pytest.mark.parametrize("bad", ["", "redis://", "sentinel-a:notaport"])
def test_a_malformed_sentinel_address_is_rejected(bad: str) -> None:
    """写错地址要在取客户端时就炸，而不是等切换那一刻才发现连不上哨兵。"""
    with pytest.raises(ValueError, match="sentinel"):
        seam._sentinel_address(bad)


def test_only_the_seam_knows_how_to_connect() -> None:
    """设计约束：端点与切换只许在缝里。调用点自己 from_url = 8 份各自为政的 failover。"""
    offenders = sorted(
        str(path.relative_to(SOURCE_ROOT))
        for path in SOURCE_ROOT.rglob("*.py")
        if path.name != "redis_client.py" and "from_url" in path.read_text(encoding="utf-8")
    )

    assert offenders == []


async def test_a_bare_url_string_behaves_like_the_topology() -> None:
    """8 个调用点里既有 URL 字符串也有拓扑对象，两者语义必须一致。"""
    client = redis_client("redis://127.0.0.1:6379/1", decode_responses=False, socket_timeout=15.0)

    assert isinstance(client, aioredis.Redis)
    kwargs = client.connection_pool.connection_kwargs
    assert kwargs["host"] == "127.0.0.1"
    assert kwargs["port"] == 6379
    assert kwargs["db"] == 1
    assert kwargs["decode_responses"] is False
    assert kwargs["socket_timeout"] == 15.0

    await client.aclose()
