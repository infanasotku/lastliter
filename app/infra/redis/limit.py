import asyncio
import math
import random
from collections.abc import Awaitable, Callable

from app.infra.redis.common import as_awaitable
from redis.asyncio import Redis

_RESERVE_SLOT_SCRIPT = """
local current_time = redis.call("TIME")
local now_us = tonumber(current_time[1]) * 1000000 + tonumber(current_time[2])
local interval_us = tonumber(ARGV[1])
local jitter_us = tonumber(ARGV[2])
local max_jitter_us = tonumber(ARGV[3])

local next_request_at = tonumber(redis.call("GET", KEYS[1])) or 0
local request_at = math.max(now_us, next_request_at)
local following_request_at = request_at + interval_us + jitter_us
local ttl_ms = math.ceil((following_request_at - now_us + interval_us + max_jitter_us) / 1000)

redis.call("SET", KEYS[1], following_request_at, "PX", ttl_ms)
return request_at - now_us
"""


class RateLimiter:
    """Redis-backed leaky bucket shared by all application replicas."""

    def __init__(
        self,
        redis: Redis,
        *,
        jitter_ratio: float = 0.1,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        randomizer: Callable[[], float] = random.random,
    ) -> None:
        if not 0 <= jitter_ratio <= 1:
            raise ValueError("jitter_ratio must be between 0 and 1")

        self._redis = redis
        self._jitter_ratio = jitter_ratio
        self._sleep = sleep
        self._randomizer = randomizer

    async def wait(self, *, key: str, limit_per_second: float) -> None:
        if limit_per_second <= 0:
            raise ValueError("limit_per_second must be greater than zero")

        interval_us = math.ceil(1_000_000 / limit_per_second)
        max_jitter_us = math.ceil(interval_us * self._jitter_ratio)
        jitter_us = int(max_jitter_us * self._randomizer())
        delay_us = int(
            await as_awaitable(
                self._redis.eval(
                    _RESERVE_SLOT_SCRIPT,
                    1,
                    key,
                    interval_us,
                    jitter_us,
                    max_jitter_us,
                )
            )
        )

        if delay_us > 0:
            await self._sleep(delay_us / 1_000_000)
