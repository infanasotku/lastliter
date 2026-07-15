from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.domains.state import PipelineType


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
    pipeline_type: PipelineType

    batch_size: int = 10
