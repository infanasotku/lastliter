from typing import Protocol

from clickhouse_connect.driver import AsyncClient

from app.infra.clickhouse.repositories.station import ClickStationRepository


class StationContext(Protocol):
    stations: ClickStationRepository


class ClickStationContext(StationContext):
    def __init__(self, client: AsyncClient) -> None:
        self.stations = ClickStationRepository(client)
