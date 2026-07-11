from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class SyncStationCmd(BaseModel):
    lat1: float
    lon1: float

    lat2: float
    lon2: float


class StartSyncStationCmd(SyncStationCmd):
    correlation_id: str


class SyncStationResult(BaseModel):
    new: int


class RawStationObservation(BaseModel):
    status: Literal["queue", "yes", "no", "low"]
    detail: str
    created_at: datetime
    author_reliable: bool
    on_site: bool


class InsertObservation(RawStationObservation):
    id: int
    station_id: str


class RunIngestionIterationCmd(BaseModel):
    owner: str


class FetchRawStationObservations(BaseModel):
    station_id: str
    observations: list[RawStationObservation]
    error: str | None = None


class StationHourlyStats(BaseModel):
    hour: int
    weekday: int

    observations_count: int

    fuel_available_ratio: float | None
    queue_probability_when_known: float | None
    queue_data_coverage_when_fuel: float | None
    bad_queue_probability_when_known: float | None
    avg_queue_severity_when_fuel: float | None

    model_config = ConfigDict(from_attributes=True)


class GetStationStatsCmd(BaseModel):
    station_id: str
