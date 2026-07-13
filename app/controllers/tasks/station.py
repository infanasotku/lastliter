from celery import shared_task
from dependency_injector.wiring import Provide, inject
from pydantic import BaseModel, Field

from app.container import Container
from app.dto.station import AddStationsByAreaCmd, AddStationsByAreaFilters
from app.infra.celery.runtime import get_runtime
from app.infra.celery.task import as_task
from app.infra.logging import get_logger
from app.services.station import StationService

logger = get_logger().getChild(__name__)


class AddStationsByAreaRequest(BaseModel):
    lat1: float
    lon1: float
    lat2: float
    lon2: float
    filters: AddStationsByAreaFilters = Field(default_factory=AddStationsByAreaFilters)


@as_task
@shared_task()
def add_stations_by_area_task(req: AddStationsByAreaRequest | dict):
    add_req = AddStationsByAreaRequest.model_validate(req)
    logger.info(
        f"Received station add by area task for bounds ({add_req.lat1}, {add_req.lon1}) - ({add_req.lat2}, {add_req.lon2})",
        extra={
            "lat1": add_req.lat1,
            "lon1": add_req.lon1,
            "lat2": add_req.lat2,
            "lon2": add_req.lon2,
            "filters": add_req.filters.model_dump(),
        },
    )
    get_runtime().run(add_stations_by_area(add_req))


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
