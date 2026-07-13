from dependency_injector.wiring import Provide, inject

from app.container import Container
from app.controllers.tasks.schemas import AddStationBySharedLinkRequest, AddStationsByAreaRequest
from app.dto.station import AddStationBySharedLinkCmd, AddStationsByAreaCmd
from app.infra.logging import get_logger
from app.services.station import StationService

logger = get_logger().getChild(__name__)


@inject
async def add_stations_by_area(
    req: AddStationsByAreaRequest,
    #
    svc: StationService = Provide[Container.station_service],
):
    logger.info(
        f"Running station add by area task handler for bounds ({req.lat1}, {req.lon1}) - ({req.lat2}, {req.lon2})",
        extra={
            "lat1": req.lat1,
            "lon1": req.lon1,
            "lat2": req.lat2,
            "lon2": req.lon2,
            "filters": req.filters.model_dump(),
        },
    )
    result = await svc.add_by_area.process(AddStationsByAreaCmd.model_validate(req.model_dump()))
    logger.info(
        f"Station add by area task handler finished with {result.inserted_count} new stations",
        extra={"new_count": result.inserted_count},
    )


@inject
async def add_station_by_shared_link(
    req: AddStationBySharedLinkRequest,
    #
    svc: StationService = Provide[Container.station_service],
):
    logger.info(
        f"Running station add by shared link task handler for link {req.shared_link}",
        extra={"shared_link": req.shared_link},
    )
    result = await svc.add_by_shared_link.process(AddStationBySharedLinkCmd.model_validate(req.model_dump()))
    logger.info(
        "Station add by shared link task handler finished",
        extra={"shared_link": req.shared_link, "inserted": result},
    )
