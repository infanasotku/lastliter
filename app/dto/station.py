from datetime import datetime
from typing import Literal

from pydantic import BaseModel


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
