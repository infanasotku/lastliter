from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Self

DEFAULT_FETCH_INTERVAL_SEC = 300  # 5 minutes
FETCH_INTERVAL_AFTER_ERROR_SEC = 600  # 10 minutes


@dataclass
class Station:
    id: str

    name: str
    address: str

    lat: float
    lon: float

    @classmethod
    def new(cls, *, id: str, name: str, address: str, lat: float, lon: float, now: datetime) -> "Station":
        return cls(
            id=id,
            name=name,
            address=address,
            lat=lat,
            lon=lon,
            last_fetched_at=datetime.min.replace(tzinfo=timezone.utc),
            next_fetch_at=now,
            fetch_interval_sec=DEFAULT_FETCH_INTERVAL_SEC,
            priority=0,
        )

    last_fetched_at: datetime
    next_fetch_at: datetime
    fetch_interval_sec: int
    description: str | None = None
    fetch_error: str | None = None
    priority: int = 0

    def update_fetch_info(self, *, now: datetime, observations_fetched: int) -> None:
        self.last_fetched_at = now
        self.next_fetch_at = now + timedelta(seconds=self.fetch_interval_sec)
        self.fetch_error = None

        # TODO: implement a more sophisticated algorithm for adjusting fetch_interval_sec and priority based on observations

    def mark_fetch_error(self, *, now: datetime, error: str) -> None:
        self.last_fetched_at = now
        self.next_fetch_at = now + timedelta(seconds=FETCH_INTERVAL_AFTER_ERROR_SEC)
        self.fetch_error = error


@dataclass(frozen=True)
class StationScore:
    hour: int
    weekday: int

    score: float

    @classmethod
    def calc_score(
        cls,
        *,
        hour: int,
        weekday: int,
        #
        fuel_available_ratio: float,
        queue_probability_when_known: float,
        normalized_avg_queue_severity: float,
        queue_data_coverage_when_fuel: float,
        bad_queue_probability_when_known: float,
        avg_queue_severity_when_fuel: float,
    ) -> Self:
        queue_penalty = queue_probability_when_known * normalized_avg_queue_severity * queue_data_coverage_when_fuel
        normalized_avg_queue_severity = avg_queue_severity_when_fuel / 4
        score = fuel_available_ratio - 0.7 * queue_penalty - 0.2 * bad_queue_probability_when_known

        return cls(
            hour=hour,
            weekday=weekday,
            score=score,
        )

    @classmethod
    def with_normalized_score(cls, score: "StationScore", max_score: float) -> "StationScore":
        return cls(
            hour=score.hour,
            weekday=score.weekday,
            score=score.score / max_score,
        )
