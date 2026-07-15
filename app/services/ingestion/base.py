from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from app.domains.state import IngestionPipelineState


class _HeartbeatStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass
class _HeartbeatContext:
    leased_states: list[IngestionPipelineState]

    status: _HeartbeatStatus
    error: str | None = None

    def retain_active(self, active_states: list[IngestionPipelineState]) -> None:
        ids = {station.station_id for station in active_states}
        self.leased_states = [station for station in self.leased_states if station.station_id in ids]

    @property
    def exhausted(self) -> bool:
        return self.status == _HeartbeatStatus.ERROR or not self.leased_states


def _station_ids(states: list[IngestionPipelineState]) -> list[str]:
    return [state.station_id for state in states]


class _IngestionIterationUC(Protocol):
    async def run(self, states: list[IngestionPipelineState]) -> None: ...
