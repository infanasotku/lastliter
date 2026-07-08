from uuid import uuid4

from dependency_injector.wiring import Provide, inject

from app.container import Container
from app.infra.common.correlation import RequestContext, with_request_context
from app.services.station import StationService


@inject
async def run_ingestion_loop(svc: StationService = Provide[Container.station_service]):
    while True:
        with with_request_context(RequestContext(request_id=str(uuid4()))):
            await svc.run_ingestion_iteration()
