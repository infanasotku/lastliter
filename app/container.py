from dependency_injector import containers, providers

from app.infra.config import generate_settings
from app.infra.http.gdebenz import HTTPGdeBenzClient


class Container(containers.DeclarativeContainer):
    settings = providers.Singleton(generate_settings)

    gdebenz = providers.Singleton(HTTPGdeBenzClient)
