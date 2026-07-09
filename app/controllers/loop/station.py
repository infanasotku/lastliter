import asyncio
import os
from uuid import uuid4

from dependency_injector.wiring import Provide, inject

from app.container import Container
from app.dto.station import RunIngestionIterationCmd
from app.infra.common.correlation import RequestContext, with_request_context
from app.services.station import StationService

IDLE_SLEEP_SECONDS = 5


@inject
async def run_ingestion_loop(svc: StationService = Provide[Container.station_service]):
    loop_id = f"{os.uname().nodename}:{os.getpid()}:{uuid4()}"
    while True:
        with with_request_context(RequestContext(request_id=str(uuid4()))):
            has_work = await svc.run_ingestion_iteration(
                RunIngestionIterationCmd(owner=loop_id),
            )

        if not has_work:
            await asyncio.sleep(IDLE_SLEEP_SECONDS)
