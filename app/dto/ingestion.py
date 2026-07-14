from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class RawStationObservation(BaseModel):
    status: Literal["queue", "yes", "no", "low"]
    detail: str
    created_at: datetime
    author_reliable: bool
    on_site: bool


class InsertObservation(RawStationObservation):
    id: int
    station_id: str


class FetchRawStationObservations(BaseModel):
    observations: list[RawStationObservation]


class RunIngestionIterationCmd(BaseModel):
    owner: str
    stage: Literal["fetch_raw"]

    batch_size: int = 10
