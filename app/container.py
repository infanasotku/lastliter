from dependency_injector import containers, providers
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infra.config import generate_settings
from app.infra.http.gdebenz import HTTPGdeBenzClient
from app.infra.postgres import create_engine
from app.infra.postgres.uows import PgStationUnitOfWork
from app.infra.redis import create_redis_context
from app.services.station import StationService


class Container(containers.DeclarativeContainer):
    settings = providers.Singleton(generate_settings)

    # Redis
    redis = providers.Resource(
        create_redis_context,
        settings.provided.redis,
    )

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

    gdebenz = providers.Singleton(HTTPGdeBenzClient)

    station_service = providers.Factory(
        StationService,
        station_uow,
        gdebenz=gdebenz,
    )
