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

    score: float | None

    @staticmethod
    def calculate_queue_penalty(
        *,
        queue_probability_when_known: float | None,
        queue_data_coverage_when_fuel: float | None,
        avg_queue_severity_when_fuel: float | None,
    ) -> float | None:
        if queue_probability_when_known is None:
            return None

        queue_coverage = queue_data_coverage_when_fuel or 0.0
        if avg_queue_severity_when_fuel is None:
            normalized_avg_queue_severity = 0.5
        else:
            normalized_avg_queue_severity = avg_queue_severity_when_fuel / 4

        return queue_probability_when_known * normalized_avg_queue_severity * queue_coverage

    @staticmethod
    def calculate_confidence(
        *,
        observations_count: int | None,
        queue_data_coverage_when_fuel: float | None,
    ) -> float | None:
        if observations_count is None:
            return None

        sample_confidence = min(observations_count / 20, 1.0)
        queue_coverage = queue_data_coverage_when_fuel or 0.0

        return 0.7 * sample_confidence + 0.3 * queue_coverage

    @staticmethod
    def clamp_score(score: float) -> float:
        return max(0.0, score)

    @classmethod
    def calc_score(
        cls,
        *,
        hour: int,
        weekday: int,
        #
        fuel_available_ratio: float | None,
        queue_probability_when_known: float | None,
        queue_data_coverage_when_fuel: float | None,
        bad_queue_probability_when_known: float | None,
        avg_queue_severity_when_fuel: float | None,
    ) -> Self:
        queue_penalty = cls.calculate_queue_penalty(
            queue_probability_when_known=queue_probability_when_known,
            queue_data_coverage_when_fuel=queue_data_coverage_when_fuel,
            avg_queue_severity_when_fuel=avg_queue_severity_when_fuel,
        )

        if fuel_available_ratio is None:
            score = None

        else:
            effective_queue_penalty = queue_penalty or 0.0
            effective_bad_queue_probability = bad_queue_probability_when_known or 0.0
            queue_uncertainty = 1.0 - (queue_data_coverage_when_fuel or 0.0)
            raw_score = (
                fuel_available_ratio
                - 0.7 * effective_queue_penalty
                - 0.2 * effective_bad_queue_probability
                - 0.2 * queue_uncertainty * fuel_available_ratio
            )
            score = cls.clamp_score(raw_score)

        return cls(
            hour=hour,
            weekday=weekday,
            score=score,
        )
