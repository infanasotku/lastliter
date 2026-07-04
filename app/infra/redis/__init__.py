from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from app.infra.config.redis import RedisSettings
from app.infra.logging.logger import get_logger
from redis.asyncio import ConnectionPool, Redis

logger = get_logger().getChild(__name__)


def _create_redis_client(settings: RedisSettings) -> Redis:
    pool = ConnectionPool.from_url(
        str(settings.dsn),
        max_connections=20,
        decode_responses=True,
        client_name=settings.client,
    )

    return Redis.from_pool(pool)


@asynccontextmanager
async def create_redis_context(settings: RedisSettings) -> AsyncGenerator[Redis]:
    redis = _create_redis_client(settings)

    await redis.ping()  # type: ignore

    try:
        yield redis
    finally:
        logger.info("Closing Redis connections")
        await redis.close()
        logger.info("Redis connections closed")
