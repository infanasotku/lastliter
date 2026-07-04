from celery import shared_task
from dependency_injector.wiring import Provide, inject
from pydantic import BaseModel

from app.container import Container
from app.dto.station import SyncStationCmd
from app.infra.celery.runtime import get_runtime
from app.infra.celery.task import as_task
from app.infra.logging import get_logger
from app.services.station import StationService

logger = get_logger().getChild(__name__)


class SyncStationRequest(BaseModel):
    lat1: float
    lon1: float
    lat2: float
    lon2: float


@as_task
@shared_task()
def sync_stations_task(req: SyncStationRequest | dict):
    sync_req = SyncStationRequest.model_validate(req)
    logger.info(
        f"Received station sync task for bounds ({sync_req.lat1}, {sync_req.lon1}) - ({sync_req.lat2}, {sync_req.lon2})",
        extra={
            "lat1": sync_req.lat1,
            "lon1": sync_req.lon1,
            "lat2": sync_req.lat2,
            "lon2": sync_req.lon2,
        },
    )
    get_runtime().run(sync_stations(sync_req))


@inject
async def sync_stations(
    req: SyncStationRequest,
    #
    svc: StationService = Provide[Container.station_service],
):
    logger.info(
        f"Running station sync task handler for bounds ({req.lat1}, {req.lon1}) - ({req.lat2}, {req.lon2})",
        extra={
            "lat1": req.lat1,
            "lon1": req.lon1,
            "lat2": req.lat2,
            "lon2": req.lon2,
        },
    )
    result = await svc.sync_stations(SyncStationCmd.model_validate(req.model_dump()))
    logger.info(
        f"Station sync task handler finished with {result.new} new stations",
        extra={"new_count": result.new},
    )
