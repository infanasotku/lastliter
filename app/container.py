from dependency_injector import containers, providers
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infra.config import generate_settings
from app.infra.http.gdebenz import HTTPGdeBenzClient
from app.infra.postgres import create_engine
from app.services.station import StationService


class Container(containers.DeclarativeContainer):
    settings = providers.Singleton(generate_settings)

    # Postgres
    read_engine = providers.Singleton(create_engine, settings.provided.postgres, tx=False)
    write_engine = providers.Singleton(create_engine, settings.provided.postgres, tx=True)
    read_sessionmaker = providers.Singleton(async_sessionmaker[AsyncSession], read_engine)
    write_sessionmaker = providers.Singleton(async_sessionmaker[AsyncSession], write_engine)

    gdebenz = providers.Singleton(HTTPGdeBenzClient)

    station_service = providers.Factory(
        StationService,
        gdebenz=gdebenz,
    )
