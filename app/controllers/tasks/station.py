from celery import shared_task

from app.controllers.tasks.schemas import AddStationBySharedLinkRequest, AddStationsByAreaRequest
from app.infra.celery.runtime import get_runtime
from app.infra.celery.task import as_task
from app.infra.logging import get_logger

logger = get_logger().getChild(__name__)


@as_task
@shared_task()
def add_stations_by_area_task(req: dict):
    from app.controllers.tasks._station import add_stations_by_area

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


@as_task
@shared_task()
def add_station_by_shared_link_task(req: dict):
    from app.controllers.tasks._station import add_station_by_shared_link

    add_req = AddStationBySharedLinkRequest.model_validate(req)
    logger.info(
        f"Received station add by shared link task for link {add_req.shared_link}",
        extra={"shared_link": add_req.shared_link},
    )
    get_runtime().run(add_station_by_shared_link(add_req))
