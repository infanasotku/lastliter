from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqladmin import Admin

from app.container import Container
from app.controllers.admin import views
from app.controllers.admin.auth import AdminAuthenticationBackend
from app.controllers.api import middlewares
from app.controllers.api import router as v1
from app.infra.logging.logger import get_logger

logger = get_logger().getChild(__name__)


def create_app() -> FastAPI:
    logger.info("Creating API application")

    container = Container()
    container.wire(
        packages=[
            "app.controllers.admin",
        ]
    )
    settings = container.settings()
    engine = container.read_engine()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        async def _await(call):
            future = call()
            if future is not None:
                await future

        await _await(container.init_resources)  # type: ignore
        try:
            yield
        finally:
            logger.info("Disposing database engines")
            await _await(container.shutdown_resources)  # type: ignore

    app = FastAPI(lifespan=lifespan)
    app.state.container = container

    app.include_router(v1, prefix="/api/v1")
    app.add_middleware(middlewares.CorrelationIdASGIMiddleware)
    logger.info("Middleware configured")

    logger.info("Creating admin panel")
    admin = Admin(
        app,
        engine,
        title="Last liter admin",
        authentication_backend=AdminAuthenticationBackend(
            settings.admin.secret,
            username=settings.admin.username,
            password=settings.admin.password,
        ),
        base_url="",
    )
    admin.add_view(views.StationView)
    logger.info("Admin panel registered")

    @app.get("/healthz", include_in_schema=False)
    async def _():
        logger.info("Healthcheck requested")
        return {"status": "ok"}

    logger.info("Admin application created")
    return app
