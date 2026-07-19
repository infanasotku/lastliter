from app.contracts.uow import UnitOfWork
from app.dto.station import StationDTO
from app.infra.clickhouse.repositories import StationContext
from app.infra.common.time import now_utc
from app.infra.logging.logger import get_logger
from app.infra.postgres.uows import StationReadContext, StationWriteContext
from app.services.station.stats import _to_domain_from_dto_score

logger = get_logger().getChild(__name__)


class GetAllStationsUC:
    def __init__(
        self,
        uow: UnitOfWork[StationReadContext, StationWriteContext],
        *,
        click_ctx: StationContext,
    ) -> None:
        self._uow = uow
        self._click_ctx = click_ctx

    async def run(self) -> list[StationDTO]:
        logger.info("Starting station list retrieval")
        async with self._uow.begin(write=False) as ctx:
            stations = await ctx.stations.get_all()

        logger.info(
            f"Fetched {len(stations)} stations from PostgreSQL",
            extra={"station_count": len(stations)},
        )
        if not stations:
            logger.info("Station list retrieval finished with no stations")
            return []

        ids = [station.id for station in stations]
        now = now_utc()
        stats = await self._click_ctx.stations.get_stations_stats_for_spot(
            station_ids=ids, hour=now.hour, weekday=now.isoweekday()
        )
        stats_count = sum(stat is not None for stat in stats)
        logger.info(
            f"Fetched current statistics for {stats_count} of {len(stations)} stations",
            extra={
                "hour": now.hour,
                "station_count": len(stations),
                "stats_count": stats_count,
                "weekday": now.isoweekday(),
            },
        )

        station_dtos = [StationDTO.from_domain(station) for station in stations]
        for station_dto, stat in zip(station_dtos, stats, strict=True):
            if stat is not None:
                score = _to_domain_from_dto_score(stat)
                station_dto.score = score.score
                station_dto.confidence = score.confidence

        scored_count = sum(station.score is not None for station in station_dtos)
        logger.info(
            f"Station list retrieval finished, {scored_count} of {len(station_dtos)} stations have a score",
            extra={
                "scored_count": scored_count,
                "station_count": len(station_dtos),
            },
        )
        return station_dtos
