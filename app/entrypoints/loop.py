import asyncio
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.container import Container
from app.controllers.loop.station import run_ingestion_loop
from app.infra.logging.logger import get_logger

logger = get_logger().getChild(__name__)


def create_app() -> FastAPI:
    logger.info("Creating loop application")

    container = Container()
    container.wire(modules=["app.controllers.loop.station"])

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        async def _await(call):
            future = call()
            if future is not None:
                await future

        await _await(container.init_resources)  # type: ignore

        async def _do():
            try:
                await run_ingestion_loop()
            except Exception:
                logger.exception("Error in ingestion loop")
                sys.exit(1)

        t = asyncio.create_task(_do())
        try:
            yield
        finally:
            logger.info("Cancelling ingestion loop")
            t.cancel()
            await t
            logger.info("Ingestion loop cancelled")

            logger.info("Disposing resources")
            await _await(container.shutdown_resources)  # type: ignore

    app = FastAPI(lifespan=lifespan)
    app.state.container = container

    @app.get("/healthz", include_in_schema=False)
    async def _():
        logger.info("Healthcheck requested")
        return {"status": "ok"}

    logger.info("Loop application created")
    return app
