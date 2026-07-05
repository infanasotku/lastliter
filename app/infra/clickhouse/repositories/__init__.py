from typing import Protocol

from app.infra.clickhouse.repositories.station import ClickStationRepository


class StationContext(Protocol):
    stations: ClickStationRepository


class ClickStationContext(StationContext):
    def __init__(self, client: ClickStationRepository) -> None:
        self.stations = client
