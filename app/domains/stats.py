from dataclasses import dataclass
from typing import Self

MAX_QUEUE_SEVERITY = 6

QUEUE_PENALTY_WEIGHT = 0.70
BAD_QUEUE_PENALTY_WEIGHT = 0.20
VERY_BAD_QUEUE_PENALTY_WEIGHT = 0.15
QUEUE_UNCERTAINTY_PENALTY_WEIGHT = 0.20
SERVICE_UNAVAILABLE_PENALTY_WEIGHT = 0.30


@dataclass(frozen=True)
class StationScore:
    hour: int
    weekday: int

    score: float | None
    confidence: float | None = None

    @staticmethod
    def clamp_score(score: float) -> float:
        return max(0.0, min(1.0, score))

    @staticmethod
    def safe_ratio(value: float | None) -> float:
        return value or 0.0

    @classmethod
    def calculate_queue_penalty(
        cls,
        *,
        queue_probability_when_known: float | None,
        queue_data_coverage_when_fuel: float | None,
        avg_queue_severity_when_fuel: float | None,
    ) -> float:
        if queue_probability_when_known is None:
            return 0.0

        queue_coverage = cls.safe_ratio(queue_data_coverage_when_fuel)

        if avg_queue_severity_when_fuel is None:
            normalized_avg_queue_severity = 0.5
        else:
            normalized_avg_queue_severity = avg_queue_severity_when_fuel / MAX_QUEUE_SEVERITY

        return queue_probability_when_known * normalized_avg_queue_severity * queue_coverage

    @classmethod
    def calculate_queue_uncertainty_penalty(
        cls,
        *,
        fuel_available_ratio: float,
        queue_data_coverage_when_fuel: float | None,
    ) -> float:
        queue_coverage = cls.safe_ratio(queue_data_coverage_when_fuel)
        queue_uncertainty = 1.0 - queue_coverage

        return fuel_available_ratio * queue_uncertainty

    @classmethod
    def calculate_total_queue_penalty(
        cls,
        *,
        fuel_available_ratio: float,
        queue_probability_when_known: float | None,
        queue_data_coverage_when_fuel: float | None,
        bad_queue_probability_when_known: float | None,
        very_bad_queue_probability_when_known: float | None,
        avg_queue_severity_when_fuel: float | None,
    ) -> float:
        queue_penalty = cls.calculate_queue_penalty(
            queue_probability_when_known=queue_probability_when_known,
            queue_data_coverage_when_fuel=queue_data_coverage_when_fuel,
            avg_queue_severity_when_fuel=avg_queue_severity_when_fuel,
        )

        queue_uncertainty_penalty = cls.calculate_queue_uncertainty_penalty(
            fuel_available_ratio=fuel_available_ratio,
            queue_data_coverage_when_fuel=queue_data_coverage_when_fuel,
        )

        return (
            QUEUE_PENALTY_WEIGHT * queue_penalty
            + BAD_QUEUE_PENALTY_WEIGHT * cls.safe_ratio(bad_queue_probability_when_known)
            + VERY_BAD_QUEUE_PENALTY_WEIGHT * cls.safe_ratio(very_bad_queue_probability_when_known)
            + QUEUE_UNCERTAINTY_PENALTY_WEIGHT * queue_uncertainty_penalty
        )

    @classmethod
    def calculate_service_penalty(
        cls,
        *,
        service_unavailable_ratio: float | None,
    ) -> float:
        return SERVICE_UNAVAILABLE_PENALTY_WEIGHT * cls.safe_ratio(service_unavailable_ratio)

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

    @classmethod
    def calc_score(
        cls,
        *,
        hour: int,
        weekday: int,
        observations_count: int | None,
        fuel_available_ratio: float | None,
        queue_probability_when_known: float | None,
        queue_data_coverage_when_fuel: float | None,
        bad_queue_probability_when_known: float | None,
        very_bad_queue_probability_when_known: float | None,
        avg_queue_severity_when_fuel: float | None,
        service_unavailable_ratio: float | None,
    ) -> Self:
        confidence = cls.calculate_confidence(
            observations_count=observations_count,
            queue_data_coverage_when_fuel=queue_data_coverage_when_fuel,
        )

        if observations_count is None or observations_count == 0:
            return cls(
                hour=hour,
                weekday=weekday,
                score=None,
                confidence=confidence,
            )

        if fuel_available_ratio is None:
            return cls(
                hour=hour,
                weekday=weekday,
                score=None,
                confidence=confidence,
            )

        queue_penalty = cls.calculate_total_queue_penalty(
            fuel_available_ratio=fuel_available_ratio,
            queue_probability_when_known=queue_probability_when_known,
            queue_data_coverage_when_fuel=queue_data_coverage_when_fuel,
            bad_queue_probability_when_known=bad_queue_probability_when_known,
            very_bad_queue_probability_when_known=very_bad_queue_probability_when_known,
            avg_queue_severity_when_fuel=avg_queue_severity_when_fuel,
        )

        service_penalty = cls.calculate_service_penalty(
            service_unavailable_ratio=service_unavailable_ratio,
        )

        raw_score = fuel_available_ratio - queue_penalty - service_penalty

        return cls(
            hour=hour,
            weekday=weekday,
            score=cls.clamp_score(raw_score),
            confidence=confidence,
        )
