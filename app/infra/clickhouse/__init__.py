from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import clickhouse_connect
from clickhouse_connect.driver import AsyncClient

from app.infra.config.clickhouse import ClickhouseSettings
from app.infra.logging.logger import get_logger

logger = get_logger().getChild(__name__)


@asynccontextmanager
async def create_clickhouse_client(settings: ClickhouseSettings) -> AsyncGenerator[AsyncClient]:
    client = await clickhouse_connect.get_async_client(
        dsn=str(settings.dsn),
    )

    async with client as c:
        yield c
        logger.info("Closing Clickhouse connections")

    logger.info("Clickhouse connections closed")
