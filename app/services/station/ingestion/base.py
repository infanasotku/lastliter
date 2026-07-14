from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from app.domains.station import Station


class _HeartbeatStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass
class _HeartbeatContext:
    leased_stations: list[Station]

    status: _HeartbeatStatus
    error: str | None = None

    def retain_active(self, active_stations: list[Station]) -> None:
        ids = {station.id for station in active_stations}
        self.leased_stations = [station for station in self.leased_stations if station.id in ids]

    @property
    def exhausted(self) -> bool:
        return self.status == _HeartbeatStatus.ERROR or not self.leased_stations


def _station_ids(stations: list[Station]) -> list[str]:
    return [station.id for station in stations]


class _IngestionIterationUC(Protocol):
    async def run(self, stations: list[Station]) -> None: ...
