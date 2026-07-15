from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Self

from app.domains.station import Station

DEFAULT_FETCH_INTERVAL_SEC = 300  # 5 minutes
FETCH_INTERVAL_AFTER_ERROR_SEC = 600  # 10 minutes


class PipelineType(StrEnum):
    FETCH_RAW = "fetch_raw"


@dataclass
class IngestionPipelineState:
    station_id: str
    pipeline_type: PipelineType

    last_processed_at: datetime
    next_run_at: datetime
    interval_sec: int
    priority: int
    meta: dict

    claimed_by: str | None = None
    lease_until: datetime | None = None
    error: str | None = None

    def update_process_info(self, now: datetime) -> None:
        self.last_processed_at = now
        self.next_run_at = now + timedelta(seconds=self.interval_sec)
        self.error = None

    def mark_process_error(self, *, now: datetime, error: str) -> None:
        self.last_processed_at = now
        self.next_run_at = now + timedelta(seconds=FETCH_INTERVAL_AFTER_ERROR_SEC)
        self.error = error

    @classmethod
    def from_station(cls, station: Station, *, now: datetime, min_time: datetime) -> list[Self]:
        return [
            cls(
                station_id=station.id,
                pipeline_type=PipelineType.FETCH_RAW,
                last_processed_at=min_time,
                next_run_at=now,
                interval_sec=DEFAULT_FETCH_INTERVAL_SEC,
                priority=0,
                meta={},
            ),
        ]
