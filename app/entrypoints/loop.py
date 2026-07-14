from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.container import Container
from app.controllers.loop.ingestion import IngestionLoop
from app.infra.logging.logger import get_logger

logger = get_logger().getChild(__name__)


def create_app() -> FastAPI:
    logger.info("Creating loop application")

    container = Container()
    container.wire(modules=["app.controllers.loop.station"])

    loop = IngestionLoop()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        async def _await(call):
            future = call()
            if future is not None:
                await future

        await _await(container.init_resources)  # type: ignore

        try:
            async with loop.run():
                yield
        finally:
            logger.info("Disposing resources")
            await _await(container.shutdown_resources)  # type: ignore
            await container.read_engine().dispose()
            await container.write_engine().dispose()

    app = FastAPI(lifespan=lifespan)
    app.state.container = container

    @app.get("/healthz", include_in_schema=False)
    async def _():
        logger.info("Healthcheck requested")
        return {"status": "ok"}

    logger.info("Loop application created")
    return app
