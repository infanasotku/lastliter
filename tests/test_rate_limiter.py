import pytest
from mock import ANY, AsyncMock
from redis.exceptions import ConnectionError as RedisConnectionError

from app.infra.redis.limit import RateLimiter


@pytest.mark.asyncio
async def test_leaky_bucket_reserves_slot_in_redis_and_sleeps_for_returned_delay():
    redis = AsyncMock()
    redis.eval = AsyncMock(return_value=500_000)
    sleep = AsyncMock()
    limiter = RateLimiter(
        redis,
        jitter_ratio=0,
        sleep=sleep,
    )

    await limiter.wait(key="station-events", limit_per_second=2)

    redis.eval.assert_awaited_once_with(ANY, 1, "station-events", 500_000, 0, 0)
    sleep.assert_awaited_once_with(0.5)


@pytest.mark.asyncio
async def test_leaky_bucket_adds_only_positive_jitter_to_redis_reservation():
    redis = AsyncMock()
    redis.eval = AsyncMock(return_value=0)
    sleep = AsyncMock()
    limiter = RateLimiter(
        redis,
        jitter_ratio=0.2,
        sleep=sleep,
        randomizer=lambda: 0.5,
    )

    await limiter.wait(key="station-events", limit_per_second=2)

    redis.eval.assert_awaited_once_with(ANY, 1, "station-events", 500_000, 50_000, 100_000)
    sleep.assert_not_awaited()


@pytest.mark.asyncio
async def test_leaky_bucket_uses_the_requested_redis_key():
    redis = AsyncMock()
    redis.eval = AsyncMock(side_effect=[0, 0])
    limiter = RateLimiter(redis, jitter_ratio=0)

    await limiter.wait(key="station-events", limit_per_second=1)
    await limiter.wait(key="station-list", limit_per_second=1)

    assert redis.eval.await_args_list[0].args[2] == "station-events"
    assert redis.eval.await_args_list[1].args[2] == "station-list"


@pytest.mark.asyncio
async def test_leaky_bucket_rejects_non_positive_rate():
    redis = AsyncMock()
    limiter = RateLimiter(redis)

    with pytest.raises(ValueError, match="greater than zero"):
        await limiter.wait(key="station-events", limit_per_second=0)

    redis.eval.assert_not_awaited()


def test_leaky_bucket_rejects_invalid_jitter_ratio():
    with pytest.raises(ValueError, match="between 0 and 1"):
        RateLimiter(AsyncMock(), jitter_ratio=1.1)


@pytest.mark.asyncio
async def test_leaky_bucket_fails_closed_when_redis_is_unavailable():
    redis = AsyncMock()
    redis.eval = AsyncMock(side_effect=RedisConnectionError("redis unavailable"))
    sleep = AsyncMock()
    limiter = RateLimiter(redis, sleep=sleep)

    with pytest.raises(RedisConnectionError, match="redis unavailable"):
        await limiter.wait(key="station-events", limit_per_second=2)

    sleep.assert_not_awaited()
