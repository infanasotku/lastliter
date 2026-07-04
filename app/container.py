from dependency_injector import containers, providers

from app.infra.config import generate_settings
from app.infra.http.gdebenz import HTTPGdeBenzClient
from app.services.station import StationService


class Container(containers.DeclarativeContainer):
    settings = providers.Singleton(generate_settings)

    gdebenz = providers.Singleton(HTTPGdeBenzClient)

    station_service = providers.Factory(
        StationService,
        gdebenz=gdebenz,
    )
