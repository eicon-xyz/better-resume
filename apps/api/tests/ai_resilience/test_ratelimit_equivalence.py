"""ai-02 等价契约：Redis 侧 Lua 桶算术 ↔ 进程内 TokenBucket（默认层，hermetic）。

审计 ai-02：`redis_buckets._TAKE_LUA` 与 `ratelimit.TokenBucket.take` 是同一套令牌桶算术的
两份手写实现——一份给跨副本共享配额，一份给 Redis 不可用时的进程内降级配额。模块 docstring 曾
自称「same arithmetic」，却没有任何测试强制：任意一侧改了 retry 口径、burst 语义或取整方式，两条
路径就会悄悄分叉而 CI 不红。本文件把那句声明变成可执行断言。

为什么不是 fakeredis 执行真 Lua：fakeredis 的 EVAL 依赖 `lupa`，它不是本仓库的依赖——缺了它
fakeredis 的 `scripting_mixin` 直接 ImportError，EVAL 退化成 `unknown command 'eval'`，CI 的
`uv sync --frozen` 同样拿不到。所以被测对象是 `redis_buckets.take_lua_math`（Lua 算术的可执行
镜像），外加一条源码级警报，挡住「有人改了 Lua 却没改镜像」。

诚实清单（本文件**没有**证明的事）：
- Lua 文本本身在本环境无法执行：真实 Redis 上的执行结果未经机器验证，只由
  `test_lua_source_still_implements_the_same_formula` 做粗粒度文本比对；
- 真实 Redis 路径还会经 Lua 的 `tostring` 往返（%.14g，约 1e-14 相对精度），镜像不模拟这层
  序列化，因此「共享配额」与「进程内配额」在尾数上仍可能有 ~1e-14 量级的相对漂移；
- 键 TTL 与 `max_identities` 懒淘汰是两种不同的过期策略，不要求等价（模块 docstring 已把它们
  列为 Redis 强制的差异），本文件不碰这条缝。
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass

import pytest

from better_resume.ai_resilience import ManualClock, ManualWallClock, TokenBucket, redis_buckets
from better_resume.ai_resilience.redis_buckets import RedisBucketStore, take_lua_math


@dataclass(frozen=True, slots=True)
class _Scenario:
    """一次完整操作序列：推进多少毫秒、连取几个令牌、手算出来的期望三元组。"""

    name: str
    rate: float
    capacity: float
    #: (advance_ms, takes)：每个场景只推进一次非零时钟。两次非零推进会让 Python 侧的浮点秒
    #: 累加与 Lua 侧的整数毫秒差出现 1 ULP 偏差（0.6 - 0.1 != 500/1000），那是两个时间基的
    #: 差异，不是算术分叉——这条缝不在本文件的契约里。
    steps: tuple[tuple[int, int], ...]
    #: 逐次 take 的 (allowed, retry_after, remaining)，手算/工具核对过的绝对值。
    expected: tuple[tuple[bool, float, int], ...]


SCENARIOS: tuple[_Scenario, ...] = (
    _Scenario(
        name="burst_drain",
        rate=2.0,
        capacity=4.0,
        steps=((0, 5),),  # 满桶连取 5 次：前 4 次放行，第 5 次拒绝
        expected=(
            (True, 0.0, 3),
            (True, 0.0, 2),
            (True, 0.0, 1),
            (True, 0.0, 0),
            (False, 0.5, 0),  # 空桶等一个令牌：1 / 2.0
        ),
    ),
    _Scenario(
        name="retry_after_fraction",
        rate=2.0,
        capacity=2.0,
        steps=((0, 2), (100, 1)),  # 取空后过 100ms 再取：补到 0.2 个令牌，仍拒绝
        expected=(
            (True, 0.0, 1),
            (True, 0.0, 0),
            (False, 0.4, 0),  # (1 - 0.2) / 2.0 —— retry 口径最容易分叉的一项
        ),
    ),
    _Scenario(
        name="exact_one_token_refill",
        rate=2.0,
        capacity=2.0,
        steps=((0, 2), (500, 1)),  # 正好补满 1 个令牌：tokens >= 1.0 的边界
        expected=(
            (True, 0.0, 1),
            (True, 0.0, 0),
            (True, 0.0, 0),  # 0.0 + 500/1000*2.0 == 1.0，两侧都必须判放行
        ),
    ),
    _Scenario(
        name="long_idle_cap",
        rate=1.0,
        capacity=2.0,
        steps=((0, 2), (100_000, 3)),  # 空闲 100s：Python 用 min(capacity, …)，Lua 用 if > cap
        expected=(
            (True, 0.0, 1),
            (True, 0.0, 0),
            (True, 0.0, 1),  # 补到 100 个令牌也必须封顶在 2
            (True, 0.0, 0),
            (False, 1.0, 0),
        ),
    ),
    _Scenario(
        name="remaining_truncation_nonint_capacity",
        rate=1.0,
        capacity=3.5,  # capacity 非整数：remaining 取整口径（int() 向零 vs math.floor）
        steps=((0, 3),),
        expected=(
            (True, 0.0, 2),  # 3.5 -> 2.5 -> int(2.5) == math.floor(2.5) == 2
            (True, 0.0, 1),
            (True, 0.0, 0),
        ),
    ),
    _Scenario(
        name="tiny_rate",
        rate=0.001,  # 极小 rate：retry 会到 1000s 量级
        capacity=1.0,
        steps=((0, 1), (0, 1), (1_000_000, 1)),
        expected=(
            (True, 0.0, 0),
            (False, 1000.0, 0),  # (1 - 0.0) / 0.001
            (True, 0.0, 0),  # 1000s 后正好补回 1 个令牌
        ),
    ),
    _Scenario(
        name="order_sensitive_refill",
        rate=0.3,
        capacity=1.0,
        # 7ms @0.3/s：(7/1000)*0.3 == 0.0021，而 (7*0.3)/1000 == 0.0021000000000000003
        # —— 同一个数学式子、不同的 double。浮点结合律不成立，这一例专门钉运算顺序。
        steps=((0, 1), (7, 1)),
        expected=(
            (True, 0.0, 0),
            (False, 3.3263333333333334, 0),  # (1 - 0.0021) / 0.3
        ),
    ),
)


def _run_lua_mirror(scenario: _Scenario) -> list[tuple[bool, float, int, float]]:
    """Redis 侧：状态由镜像自己的返回值推进（不用第二份算术重新实现状态更新）。"""
    tokens: float | None = None
    ts_ms: float | None = None
    now_ms = 0
    results: list[tuple[bool, float, int, float]] = []
    for advance_ms, takes in scenario.steps:
        now_ms += advance_ms
        for _ in range(takes):
            allowed, retry_after, remaining, tokens, ts_ms = take_lua_math(
                tokens=tokens,
                ts_ms=ts_ms,
                now_ms=now_ms,
                rate=scenario.rate,
                capacity=scenario.capacity,
            )
            results.append((allowed, retry_after, remaining, tokens))
    return results


def _run_token_bucket(scenario: _Scenario) -> list[tuple[bool, float, int, float]]:
    """Python 侧（算术权威）：ManualClock 推进，并读回权威状态以便按位比较。"""
    clock = ManualClock()
    bucket = TokenBucket(rate=scenario.rate, capacity=scenario.capacity, clock=clock)
    results: list[tuple[bool, float, int, float]] = []
    for advance_ms, takes in scenario.steps:
        if advance_ms:
            clock.advance(advance_ms / 1000)
        for _ in range(takes):
            allowed, retry_after, remaining = bucket.take()
            # 只读私有状态：三个对外返回值会把 1 ULP 的顺序差异吃掉（floor / 0.0 / 1e-9 容差），
            # 按位等价必须看原始 tokens。 # noqa: SLF001 - 按位比较需要权威状态
            results.append((allowed, retry_after, remaining, bucket._tokens))
    return results


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda scenario: scenario.name)
def test_lua_mirror_matches_hand_computed_vectors(scenario: _Scenario) -> None:
    """镜像函数的 allowed / retry_after / remaining 必须逐次等于场景表里的期望值。"""
    results = _run_lua_mirror(scenario)

    assert len(results) == len(scenario.expected)
    for step, (got, want) in enumerate(zip(results, scenario.expected, strict=True)):
        allowed, retry_after, remaining, _ = got
        want_allowed, want_retry, want_remaining = want
        where = f"{scenario.name} step {step}"
        assert allowed is want_allowed, where
        assert remaining == want_remaining, where
        assert retry_after == pytest.approx(want_retry, rel=1e-9), where


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda scenario: scenario.name)
def test_token_bucket_and_lua_mirror_never_disagree(scenario: _Scenario) -> None:
    """等价断言：同一张场景表驱动两条路径，逐项比较三个对外返回值（外加原始状态）。

    审计 ai-02 要的就是这一条：降级后的进程内配额与 Redis 共享配额，对同一串操作必须给出同一个
    allowed / retry_after / remaining。最后那条 tokens 比较是刻意的：把运算顺序从
    `elapsed / 1000 * rate` 换成 `elapsed * rate / 1000` 只差 1 ULP，前三项（floor、0.0、
    1e-9 容差）全都看不见它——只有按位比较才钉得住浮点结合律。
    """
    python_side = _run_token_bucket(scenario)
    lua_side = _run_lua_mirror(scenario)

    assert len(python_side) == len(lua_side)
    for step, (py, lua) in enumerate(zip(python_side, lua_side, strict=True)):
        allowed_py, retry_py, remaining_py, tokens_py = py
        allowed_lua, retry_lua, remaining_lua, tokens_lua = lua
        where = f"{scenario.name} step {step}"
        assert allowed_lua is allowed_py, where
        assert remaining_lua == remaining_py, where
        assert retry_lua == pytest.approx(retry_py, rel=1e-9), where
        # 两侧跑的是同一串 IEEE754 双精度运算、同一份输入状态与同一口径的时钟，必须逐位相等。
        assert tokens_lua == tokens_py, where


def test_lua_source_still_implements_the_same_formula() -> None:
    """源码级警报（粗粒度，不等于证明等价）：Lua 在本环境跑不了，这条保证它没被改走。

    下面几条式子是 `take_lua_math` 逐行镜像的对象。谁改了 Lua 的算术，就必须同步改镜像，
    否则 `test_token_bucket_and_lua_mirror_never_disagree` 的等价断言会失真。
    """
    script = redis_buckets._TAKE_LUA
    for formula in (
        "elapsed / 1000 * rate",
        "tokens > cap",
        "tokens >= 1",
        "(1 - tokens) / rate",
        "math.floor(tokens)",
    ):
        assert formula in script, f"_TAKE_LUA 里的 {formula!r} 不见了；改 Lua 必须两处同改"

    take_source = inspect.getsource(RedisBucketStore.take)
    assert "_TAKE_LUA" in take_source, "RedisBucketStore.take 必须跑 _TAKE_LUA，不能另起第二个脚本"


class _RecordingRedis:
    """假 Redis 客户端（系统边界替身）：记录 eval 入参，回放 Lua 会回的那串字符串。"""

    def __init__(self, replies: list[list[object]]) -> None:
        self._replies = list(replies)
        self.calls: list[tuple[str, int, tuple[object, ...]]] = []

    async def eval(self, script: str, numkeys: int, *args: object) -> list[object]:
        self.calls.append((script, numkeys, args))
        return self._replies.pop(0)

    async def aclose(self) -> None:
        return None


async def test_store_take_evals_the_lua_and_converts_its_string_reply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """已知差异（原规格第 4 项）：Lua 的数字回来是字符串，存储层必须转成 bool/float/int。

    顺带钉住「跑的就是 _TAKE_LUA」：eval 的 numkeys 与 ARGV 顺序
    （now_ms / rate / capacity / ttl_ms）就是脚本按下标读的那几个。
    """
    fake = _RecordingRedis([[1, "0", "3"], [0, "0.5", "0"]])
    monkeypatch.setattr(redis_buckets, "redis_client", lambda *args, **kwargs: fake)
    store = RedisBucketStore("redis://unused", clock=ManualWallClock(0))

    first = await store.take("ai_call|session:abc", rate=2.0, capacity=4.0)
    second = await store.take("ai_call|session:abc", rate=2.0, capacity=4.0)
    await store.aclose()

    assert first == (True, 0.0, 3)
    assert second == (False, 0.5, 0)
    assert [type(value) for value in first] == [bool, float, int]  # 字符串没漏出去

    script, numkeys, args = fake.calls[0]
    assert script is redis_buckets._TAKE_LUA
    assert numkeys == 1
    assert args[0] == "br:rl:ai_call|session:abc"
    assert args[1] == 0  # now_ms 来自注入的 ManualWallClock
    assert args[2] == "2.0"
    assert args[3] == "4.0"
