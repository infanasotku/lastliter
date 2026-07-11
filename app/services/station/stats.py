from app.domains.station import StationScore
from app.dto.station import GetStationStatsCmd
from app.infra.clickhouse.repositories import StationContext


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

        scores = [
            StationScore.calc_score(
                hour=stat.hour,
                weekday=stat.weekday,
                #
                fuel_available_ratio=stat.fuel_available_ratio,
                queue_probability_when_known=stat.queue_probability_when_known,
                normalized_avg_queue_severity=stat.normalized_avg_queue_severity,
                queue_data_coverage_when_fuel=stat.queue_data_coverage_when_fuel,
                bad_queue_probability_when_known=stat.bad_queue_probability_when_known,
                avg_queue_severity_when_fuel=stat.avg_queue_severity_when_fuel,
            )
            for stat in stats
        ]
        max_score = max(score.score for score in scores)

        return [StationScore.with_normalized_score(score, max_score) for score in scores]
