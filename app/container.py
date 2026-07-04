from dependency_injector import containers, providers

from app.infra.config import generate_settings


class Container(containers.DeclarativeContainer):
    settings = providers.Singleton(generate_settings)
