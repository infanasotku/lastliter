from app.contracts.uow import UnitOfWork
from app.dto.station import (
    StartSyncStationCmd,
    SyncStationCmd,
    SyncStationResult,
)
from app.infra.clickhouse.repositories import StationContext
from app.infra.http.gdebenz import HTTPGdeBenzClient
from app.infra.logging import get_logger
from app.infra.postgres.uows import StationReadContext, StationWriteContext
from app.infra.redis.limit import RateLimiter
from app.services.station.ingestion import RunIngestionIterationUC

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
            },
        )
        req = SyncStationRequest(
            lat1=cmd.lat1,
            lon1=cmd.lon1,
            lat2=cmd.lat2,
            lon2=cmd.lon2,
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
            },
        )
        stations = await self._gdebenz.get_stations(
            lat1=cmd.lat1,
            lon1=cmd.lon1,
            lat2=cmd.lat2,
            lon2=cmd.lon2,
        )
        filtered_stations = [s for s in stations if s.address != "" and s.name != ""]
        logger.info(
            f"Fetched {len(stations)} stations, {len(filtered_stations)} passed validation",
            extra={
                "fetched_count": len(stations),
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

    async def run_ingestion_iteration(self) -> bool:
        return await RunIngestionIterationUC(
            uow=self._uow,
            click_ctx=self._click_ctx,
            gdebenz=self._gdebenz,
            limiter=self._limiter,
        ).run()
