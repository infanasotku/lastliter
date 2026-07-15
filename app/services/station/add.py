from datetime import datetime, timezone
from itertools import chain

from app.contracts.uow import UnitOfWork
from app.domains.state import IngestionPipelineState
from app.domains.station import Station
from app.dto.station import (
    AddStationBySharedLinkCmd,
    AddStationsByAreaCmd,
    AddStationsByAreaResult,
    StartAddStationBySharedLinkCmd,
    StartAddStationsByAreaCmd,
)
from app.infra.common.time import now_utc
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
        async with self._uow.begin(write=True) as ctx:
            inserted_stations = await ctx.stations.insert_many_safe(filtered_stations)
            await sync_pipeline_states(ctx, inserted_stations=inserted_stations)

        logger.info(
            f"Station add by area finished, inserted {len(inserted_stations)} new stations",
            extra={
                "inserted_count": len(inserted_stations),
                "valid_count": len(filtered_stations),
            },
        )
        return AddStationsByAreaResult(
            inserted_count=len(inserted_stations),
        )


class AddStationBySharedLinkUC:
    def __init__(
        self,
        uow: UnitOfWork[StationReadContext, StationWriteContext],
        *,
        gdebenz: HTTPGdeBenzClient,
    ) -> None:
        self._uow = uow
        self._gdebenz = gdebenz

    async def start(self, cmd: StartAddStationBySharedLinkCmd) -> None:
        from app.controllers.tasks.station import AddStationBySharedLinkRequest, add_station_by_shared_link_task

        logger.info(
            f"Scheduling station add by shared link task for link {cmd.shared_link}",
            extra={
                "correlation_id": cmd.correlation_id,
                "shared_link": cmd.shared_link,
            },
        )
        req = AddStationBySharedLinkRequest(shared_link=cmd.shared_link)
        add_station_by_shared_link_task.apply_async(kwargs={"req": req.model_dump()}, task_id=cmd.correlation_id)
        logger.info(
            f"Station add by shared link task scheduled with task id {cmd.correlation_id}",
            extra={"task_id": cmd.correlation_id, "shared_link": cmd.shared_link},
        )

    async def process(self, cmd: AddStationBySharedLinkCmd) -> bool:
        logger.info(
            f"Starting station add by shared link for link {cmd.shared_link}",
            extra={"shared_link": cmd.shared_link},
        )
        station = await self._gdebenz.get_station_by_shared_link(cmd.shared_link)
        if station is None:
            logger.warning(
                f"Station not found by shared link {cmd.shared_link}",
                extra={"shared_link": cmd.shared_link},
            )
            return False

        async with self._uow.begin(write=True) as ctx:
            inserted_stations = await ctx.stations.insert_many_safe([station])
            await sync_pipeline_states(ctx, inserted_stations=inserted_stations)

        logger.info(
            f"Station add by shared link finished, inserted {len(inserted_stations)} new stations",
            extra={
                "inserted_count": len(inserted_stations),
                "station_id": station.id,
                "station_name": station.name,
            },
        )

        return len(inserted_stations) > 0


async def sync_pipeline_states(
    ctx: StationWriteContext,
    *,
    inserted_stations: list[Station],
) -> None:
    pipes = list(
        chain(
            *(
                IngestionPipelineState.from_station(
                    station, now=now_utc(), min_time=datetime.min.replace(tzinfo=timezone.utc)
                )
                for station in inserted_stations
            )
        )
    )

    inserted = await ctx.states.insert_many_safe(pipes)
    logger.info(
        f"Station pipeline state sync finished, inserted {inserted} pipeline states for {len(inserted_stations)} stations",
        extra={
            "inserted_pipeline_states_count": inserted,
            "inserted_stations_count": len(inserted_stations),
            "station_ids": [station.id for station in inserted_stations],
        },
    )
