from app.contracts.uow import UnitOfWork
from app.domains.station import Station
from app.dto.station import AddStationsByAreaCmd, AddStationsByAreaResult, StartAddStationsByAreaCmd
from app.infra.http.gdebenz import HTTPGdeBenzClient
from app.infra.logging.logger import get_logger
from app.infra.postgres.uows import StationReadContext, StationWriteContext

logger = get_logger().getChild(__name__)


class AddStationsByAreaUC:
    def __init__(
        self,
        uow: UnitOfWork[StationReadContext, StationWriteContext],
        *,
        gdebenz: HTTPGdeBenzClient,
    ) -> None:
        self._uow = uow
        self._gdebenz = gdebenz

    async def start(self, cmd: StartAddStationsByAreaCmd) -> None:
        from app.controllers.tasks.station import AddStationsByAreaRequest, add_stations_by_area_task

        logger.info(
            f"Scheduling station add by area task for bounds ({cmd.lat1}, {cmd.lon1}) - ({cmd.lat2}, {cmd.lon2})",
            extra={
                "correlation_id": cmd.correlation_id,
                "lat1": cmd.lat1,
                "lon1": cmd.lon1,
                "lat2": cmd.lat2,
                "lon2": cmd.lon2,
                "filters": cmd.filters.model_dump(),
            },
        )
        req = AddStationsByAreaRequest(
            lat1=cmd.lat1,
            lon1=cmd.lon1,
            lat2=cmd.lat2,
            lon2=cmd.lon2,
            filters=cmd.filters,
        )
        add_stations_by_area_task.apply_async(kwargs={"req": req.model_dump()}, task_id=cmd.correlation_id)
        logger.info(
            f"Station add by area task scheduled with task id {cmd.correlation_id}",
            extra={"task_id": cmd.correlation_id},
        )

    async def process(self, cmd: AddStationsByAreaCmd) -> AddStationsByAreaResult:
        logger.info(
            f"Starting station add by area for bounds ({cmd.lat1}, {cmd.lon1}) - ({cmd.lat2}, {cmd.lon2})",
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
                if cmd.filters.by_name.lower() not in s.name.lower():
                    return False

            if cmd.filters.by_id is not None:
                if cmd.filters.by_id != s.id:
                    return False

            return True

        filtered_stations = [s for s in stations if filter_station(s)]
        logger.info(
            f"Fetched {len(stations)} stations, {len(filtered_stations)} passed validation",
            extra={
                "fetched_count": len(stations),
                "by_id": cmd.filters.by_id,
                "by_name": cmd.filters.by_name,
                "valid_count": len(filtered_stations),
                "skipped_count": len(stations) - len(filtered_stations),
            },
        )
        async with self._uow.begin(write=True) as uow:
            inserted_stations = await uow.stations.insert_many_safe(filtered_stations)

        logger.info(
            f"Station add by area finished, inserted {inserted_stations} new stations",
            extra={
                "inserted_count": inserted_stations,
                "valid_count": len(filtered_stations),
            },
        )
        return AddStationsByAreaResult(
            inserted_count=inserted_stations,
        )
