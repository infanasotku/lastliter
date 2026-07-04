from dependency_injector.wiring import Provide, inject

from app.container import Container
from app.services.station import StationService


@inject
async def run_ingestion_loop(svc: StationService = Provide[Container.station_service]):
    await svc.run_ingestion_loop()
