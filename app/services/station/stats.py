from app.domains.stats import StationScore
from app.dto.station import GetStationStatsCmd, StationHourlyStats
from app.infra.clickhouse.repositories import StationContext


def _to_domain_from_dto_score(stat: StationHourlyStats) -> StationScore:
    return StationScore.calc_score(
        hour=stat.hour,
        weekday=stat.weekday,
        observations_count=stat.observations_count,
        #
        fuel_available_ratio=stat.fuel_available_ratio,
        queue_probability_when_known=stat.queue_probability_when_known,
        queue_data_coverage_when_fuel=stat.queue_data_coverage_when_fuel,
        bad_queue_probability_when_known=stat.bad_queue_probability_when_known,
        avg_queue_severity_when_fuel=stat.avg_queue_severity_when_fuel,
        very_bad_queue_probability_when_known=stat.very_bad_queue_probability_when_known,
        service_unavailable_ratio=stat.service_unavailable_ratio,
    )


class GetStationStatsUC:
    def __init__(
        self,
        click_ctx: StationContext,
    ):
        self._click_ctx = click_ctx

    async def run(self, cmd: GetStationStatsCmd) -> list[StationScore]:
        stats = await self._click_ctx.stations.get_station_hourly_stats(
            station_id=cmd.station_id,
        )
        if not stats:
            return []

        return [_to_domain_from_dto_score(stat) for stat in stats]
