import asyncio
import os
from uuid import uuid4

from dependency_injector.wiring import Provide, inject

from app.container import Container
from app.dto.station import RunIngestionIterationCmd
from app.infra.common.correlation import RequestContext, with_request_context
from app.infra.logging.logger import get_logger
from app.services.station import StationService

IDLE_SLEEP_SECONDS = 5

logger = get_logger().getChild(__name__)


@inject
async def run_ingestion_loop(svc: StationService = Provide[Container.station_service]):
    loop_id = f"{os.uname().nodename}:{os.getpid()}:{uuid4()}"
    logger.info(f"Starting station ingestion loop with owner {loop_id}", extra={"owner": loop_id})
    while True:
        with with_request_context(RequestContext(request_id=str(uuid4()))):
            logger.info(f"Starting station ingestion loop iteration for owner {loop_id}", extra={"owner": loop_id})
            has_work = await svc.run_ingestion_iteration(
                RunIngestionIterationCmd(owner=loop_id),
            )
            logger.info(
                f"Station ingestion loop iteration finished for owner {loop_id}: has_work={has_work}",
                extra={"owner": loop_id, "has_work": has_work},
            )

        if not has_work:
            logger.info(
                f"Station ingestion loop is idle for owner {loop_id}, sleeping {IDLE_SLEEP_SECONDS} seconds",
                extra={"owner": loop_id, "idle_sleep_seconds": IDLE_SLEEP_SECONDS},
            )
            await asyncio.sleep(IDLE_SLEEP_SECONDS)
