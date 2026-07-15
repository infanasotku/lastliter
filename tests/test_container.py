from unittest.mock import Mock

from dependency_injector import providers

from app.container import Container
from app.infra.clickhouse.repositories import ClickStationContext
from app.infra.config import TestSettings as AppTestSettings
from app.infra.postgres.uows import PgStationUnitOfWork
from app.services.ingestion import IngestionService
from app.services.station import StationService


def test_infrastructure_dependencies_are_created_with_settings():
    container = Container()
    settings = AppTestSettings()
    redis = object()
    read_engine = object()
    write_engine = object()
    clickhouse_client = object()
    gdebenz = object()
    limiter = object()

    settings_factory = Mock(return_value=settings)
    redis_factory = Mock(return_value=redis)
    engine_factory = Mock(side_effect=[read_engine, write_engine])
    clickhouse_factory = Mock(return_value=clickhouse_client)
    gdebenz_factory = Mock(return_value=gdebenz)
    limiter_factory = Mock(return_value=limiter)
    container.settings.set_provides(settings_factory)
    container.redis.set_provides(redis_factory)
    container.read_engine.set_provides(engine_factory)
    container.write_engine.set_provides(engine_factory)
    container.clickhouse_client.set_provides(clickhouse_factory)
    container.gdebenz.set_provides(gdebenz_factory)
    container.limiter.set_provides(limiter_factory)

    assert container.settings() is settings
    assert container.redis() is redis
    assert container.read_engine() is read_engine
    assert container.write_engine() is write_engine
    assert container.clickhouse_client() is clickhouse_client
    assert container.gdebenz() is gdebenz
    assert container.limiter() is limiter

    settings_factory.assert_called_once_with()
    redis_factory.assert_called_once_with(settings.redis)
    assert engine_factory.call_args_list == [
        ((settings.postgres,), {"tx": False}),
        ((settings.postgres,), {"tx": True}),
    ]
    clickhouse_factory.assert_called_once_with(settings.clickhouse)
    gdebenz_factory.assert_called_once_with(settings.gdebenz)
    limiter_factory.assert_called_once_with()


def test_postgres_and_clickhouse_dependencies_receive_infrastructure_resources():
    container = Container()
    read_engine = object()
    write_engine = object()
    read_sessionmaker = object()
    write_sessionmaker = object()
    clickhouse_client = object()
    sessionmaker_factory = Mock(side_effect=[read_sessionmaker, write_sessionmaker])
    container.read_engine.override(providers.Object(read_engine))
    container.write_engine.override(providers.Object(write_engine))
    container.read_sessionmaker.set_provides(sessionmaker_factory)
    container.write_sessionmaker.set_provides(sessionmaker_factory)
    container.clickhouse_client.override(providers.Object(clickhouse_client))

    uow = container.uow()
    station_ctx = container.station_ctx()

    assert isinstance(uow, PgStationUnitOfWork)
    assert uow._read_sessionmaker is read_sessionmaker
    assert uow._write_sessionmaker is write_sessionmaker
    assert sessionmaker_factory.call_args_list == [
        ((read_engine,), {}),
        ((write_engine,), {}),
    ]
    assert isinstance(station_ctx, ClickStationContext)
    assert station_ctx.stations._client is clickhouse_client


def test_services_receive_all_dependencies():
    container = Container()
    uow = object()
    gdebenz = object()
    limiter = object()
    station_ctx = object()
    container.uow.override(providers.Object(uow))
    container.gdebenz.override(providers.Object(gdebenz))
    container.limiter.override(providers.Object(limiter))
    container.station_ctx.override(providers.Object(station_ctx))

    station_service = container.station_service()
    ingestion_service = container.ingestion_service()

    assert isinstance(station_service, StationService)
    assert station_service._uow is uow
    assert station_service._gdebenz is gdebenz
    assert station_service._click_ctx is station_ctx
    assert isinstance(ingestion_service, IngestionService)
    assert ingestion_service._uow is uow
    assert ingestion_service._gdebenz is gdebenz
    assert ingestion_service._limiter is limiter
    assert ingestion_service._click_ctx is station_ctx
