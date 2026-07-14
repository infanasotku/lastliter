from dependency_injector import containers, providers
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infra.clickhouse import create_clickhouse_client
from app.infra.clickhouse.repositories import ClickStationContext
from app.infra.config import generate_settings
from app.infra.http.gdebenz import create_gdebenz_client
from app.infra.postgres import create_engine
from app.infra.postgres.uows import PgStationUnitOfWork
from app.infra.redis import create_redis_context
from app.infra.redis.limit import RateLimiter
from app.services.ingestion import IngestionService
from app.services.station import StationService


class Container(containers.DeclarativeContainer):
    settings = providers.Singleton(generate_settings)

    # Redis
    redis = providers.Resource(
        create_redis_context,
        settings.provided.redis,
    )
    limiter = providers.Singleton(RateLimiter)

    # Postgres
    read_engine = providers.Singleton(create_engine, settings.provided.postgres, tx=False)
    write_engine = providers.Singleton(create_engine, settings.provided.postgres, tx=True)
    read_sessionmaker = providers.Singleton(async_sessionmaker[AsyncSession], read_engine)
    write_sessionmaker = providers.Singleton(async_sessionmaker[AsyncSession], write_engine)

    station_uow = providers.Factory(
        PgStationUnitOfWork,
        read_sessionmaker=read_sessionmaker,
        write_sessionmaker=write_sessionmaker,
    )

    # Clickhouse
    clickhouse_client = providers.Resource(
        create_clickhouse_client,
        settings.provided.clickhouse,
    )

    station_ctx = providers.Singleton(ClickStationContext, clickhouse_client)

    # HTTP
    gdebenz = providers.Resource(create_gdebenz_client, settings.provided.gdebenz)

    # Svc
    station_service = providers.Factory(
        StationService,
        station_uow,
        gdebenz=gdebenz,
        limiter=limiter,
        click_ctx=station_ctx,
    )
    ingestion_service = providers.Factory(
        IngestionService,
        station_uow,
        gdebenz=gdebenz,
        limiter=limiter,
        click_ctx=station_ctx,
    )
