from celery import shared_task
from dependency_injector.wiring import Provide, inject
from pydantic import BaseModel

from app.container import Container
from app.dto.station import SyncStationCmd
from app.infra.celery.runtime import get_runtime
from app.infra.celery.task import as_task
from app.services.station import StationService


class SyncStationRequest(BaseModel):
    lat1: float
    lon1: float
    lat2: float
    lon2: float


@as_task
@shared_task()
def sync_stations_task(req: SyncStationRequest | dict):
    get_runtime().run(sync_stations(SyncStationRequest.model_validate(req)))


@inject
async def sync_stations(
    req: SyncStationRequest,
    #
    svc: StationService = Provide[Container.station_service],
):
    await svc.sync_stations(SyncStationCmd.model_validate(req.model_dump()))
