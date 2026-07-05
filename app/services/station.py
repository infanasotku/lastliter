from uuid import uuid4

from app.contracts.uow import UnitOfWork
from app.domains.station import Station
from app.dto.station import RawStationObservation, StartSyncStationCmd, SyncStationCmd, SyncStationResult
from app.infra.common.time import now_utc
from app.infra.http.gdebenz import HTTPGdeBenzClient
from app.infra.logging import get_logger
from app.infra.postgres.uows import StationReadContext, StationWriteContext
from app.infra.redis.common import KEY_PREFIX
from app.infra.redis.limit import RateLimiter

logger = get_logger().getChild(__name__)


class StationService:
    def __init__(
        self,
        uow: UnitOfWork[StationReadContext, StationWriteContext],
        *,
        gdebenz: HTTPGdeBenzClient,
        limiter: RateLimiter,
    ) -> None:
        self._uow = uow
        self._gdebenz = gdebenz
        self._limiter = limiter

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

    async def run_ingestion_loop(self) -> None:
        ITERATION_BATCH_SIZE = 10
        EVENTS_LIMIT_PER_STATION = 20
        LIMIT_KEY = KEY_PREFIX + "stations:fetch:limit"
        LIMIT_PER_SECOND = 2

        async def _fetch_observations(stations: list[Station]) -> dict[str, list[RawStationObservation]]:
            station_obs_dict: dict[str, list[RawStationObservation]] = {}

            for station in stations:
                await self._limiter.wait(key=LIMIT_KEY, limit_per_second=LIMIT_PER_SECOND)
                station_obs_dict[station.id] = await self._gdebenz.get_obs_by_id(
                    station.id, limit=EVENTS_LIMIT_PER_STATION
                )

            return station_obs_dict

        async def _process_observations(
            stations: list[Station], station_obs_dict: dict[str, list[RawStationObservation]]
        ) -> None:
            for station in stations:
                obs = station_obs_dict.get(station.id, [])

        while True:
            iteration_id = uuid4()

            async with self._uow.begin(write=True) as ctx:
                stations = await ctx.stations.get_stations_for_fetch_for_update(
                    now=now_utc(),
                    limit=ITERATION_BATCH_SIZE,
                )
                obs = await _fetch_observations(stations)
                await _process_observations(stations, obs)
