"""Test-side timing helpers.

`settle` only yields the event loop: it moves no clock and burns no real time, so it cannot
hide a timing assumption. Anything that must *wait* for a condition goes through
`better_resume.ai_resilience.wait_until`, the single bounded wait primitive.
"""

from __future__ import annotations

import asyncio


async def settle(turns: int = 1) -> None:
    for _ in range(turns):
        await asyncio.sleep(0)  # 允许：只让出事件循环，不推进时钟、不等待真实时间
