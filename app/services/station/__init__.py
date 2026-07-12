from app.contracts.uow import UnitOfWork
from app.domains.station import Station, StationScore
from app.dto.station import (
    GetStationStatsCmd,
    RunIngestionIterationCmd,
    StartSyncStationCmd,
    SyncStationCmd,
    SyncStationResult,
)
from app.infra.clickhouse.repositories import StationContext
from app.infra.http.gdebenz import HTTPGdeBenzClient
from app.infra.logging import get_logger
from app.infra.postgres.uows import StationReadContext, StationWriteContext
from app.infra.redis.limit import RateLimiter

logger = get_logger().getChild(__name__)


class StationService:
    def __init__(
        self,
        uow: UnitOfWork[StationReadContext, StationWriteContext],
        *,
        click_ctx: StationContext,
        gdebenz: HTTPGdeBenzClient,
        limiter: RateLimiter,
    ) -> None:
        self._uow = uow
        self._gdebenz = gdebenz
        self._limiter = limiter
        self._click_ctx = click_ctx

    async def start_sync_stations(self, cmd: StartSyncStationCmd) -> None:
        from app.controllers.tasks.station import SyncStationRequest, sync_stations_task

        logger.info(
            f"Scheduling station sync task for bounds ({cmd.lat1}, {cmd.lon1}) - ({cmd.lat2}, {cmd.lon2})",
            extra={
                "correlation_id": cmd.correlation_id,
                "lat1": cmd.lat1,
                "lon1": cmd.lon1,
                "lat2": cmd.lat2,
                "lon2": cmd.lon2,
                "filters": cmd.filters.model_dump(),
            },
        )
        req = SyncStationRequest(
            lat1=cmd.lat1,
            lon1=cmd.lon1,
            lat2=cmd.lat2,
            lon2=cmd.lon2,
            filters=cmd.filters,
        )
        sync_stations_task.apply_async(kwargs={"req": req.model_dump()}, task_id=cmd.correlation_id)
        logger.info(
            f"Station sync task scheduled with task id {cmd.correlation_id}",
            extra={"task_id": cmd.correlation_id},
        )

    async def sync_stations(self, cmd: SyncStationCmd) -> SyncStationResult:
        logger.info(
            f"Starting station sync for bounds ({cmd.lat1}, {cmd.lon1}) - ({cmd.lat2}, {cmd.lon2})",
            extra={
                "lat1": cmd.lat1,
                "lon1": cmd.lon1,
                "lat2": cmd.lat2,
                "lon2": cmd.lon2,
                "filters": cmd.filters.model_dump(),
            },
        )
        stations = await self._gdebenz.get_stations(
            lat1=cmd.lat1,
            lon1=cmd.lon1,
            lat2=cmd.lat2,
            lon2=cmd.lon2,
        )

        def filter_station(s: Station) -> bool:
            if not s.address or not s.name:
                return False

            if cmd.filters.by_name is not None:
                return cmd.filters.by_name.lower() in s.name.lower()

            return True

        filtered_stations = [s for s in stations if filter_station(s)]
        logger.info(
            f"Fetched {len(stations)} stations, {len(filtered_stations)} passed validation",
            extra={
                "fetched_count": len(stations),
                "by_name": cmd.filters.by_name,
                "valid_count": len(filtered_stations),
                "skipped_count": len(stations) - len(filtered_stations),
            },
        )
        async with self._uow.begin(write=True) as uow:
            inserted_stations = await uow.stations.insert_many_safe(filtered_stations)

        logger.info(
            f"Station sync finished, inserted {inserted_stations} new stations",
            extra={
                "inserted_count": inserted_stations,
                "valid_count": len(filtered_stations),
            },
        )
        return SyncStationResult(
            new=inserted_stations,
        )

    # Single UC

    async def run_ingestion_iteration(self, cmd: RunIngestionIterationCmd) -> bool:
        from app.services.station.ingestion import RunIngestionIterationUC

        return await RunIngestionIterationUC(
            uow=self._uow,
            click_ctx=self._click_ctx,
            gdebenz=self._gdebenz,
            limiter=self._limiter,
        ).run(cmd)

    async def get_station_stats(self, cmd: GetStationStatsCmd) -> list[StationScore]:
        from app.services.station.stats import GetStationStatsUC

        return await GetStationStatsUC(
            click_ctx=self._click_ctx,
        ).run(cmd)
