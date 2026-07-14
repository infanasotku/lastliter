import asyncio
import os
import sys
from contextlib import asynccontextmanager, suppress
from uuid import uuid4

from dependency_injector.wiring import Provide, inject

from app.container import Container
from app.dto.ingestion import RunIngestionIterationCmd
from app.infra.common.correlation import RequestContext, with_request_context
from app.infra.logging.logger import get_logger
from app.services.station import StationService

IDLE_SLEEP_SECONDS = 5

FETCH_RAW_BATCH_SIZE = 10

logger = get_logger().getChild(__name__)


class IngestionLoop:
    def __init__(self):
        self._loop_id = f"{os.uname().nodename}:{os.getpid()}:{uuid4()}"
        self._logger = logger.getChild(self.__class__.__name__)

    @inject
    async def _run_loop(
        self,
        cmd: RunIngestionIterationCmd,
        #
        svc: StationService = Provide[Container.station_service],
    ):
        loop_id = self._loop_id
        logger = self._logger

        logger.info(
            f"Starting {cmd.stage} station ingestion loop with owner {loop_id}",
            extra={"owner": loop_id, "stage": cmd.stage},
        )
        while True:
            with with_request_context(RequestContext(request_id=str(uuid4()))):
                logger.info(
                    f"Starting {cmd.stage} station ingestion loop iteration for owner {loop_id}",
                    extra={"owner": loop_id, "stage": cmd.stage},
                )
                has_work = await svc.run_ingestion_iteration(cmd)
                logger.info(
                    f"{cmd.stage} station ingestion loop iteration finished for owner {loop_id}: has_work={has_work}",
                    extra={"owner": loop_id, "stage": cmd.stage, "has_work": has_work},
                )

            if not has_work:
                logger.info(
                    f"{cmd.stage} station ingestion loop is idle for owner {loop_id}, sleeping {IDLE_SLEEP_SECONDS} seconds",
                    extra={"owner": loop_id, "stage": cmd.stage, "idle_sleep_seconds": IDLE_SLEEP_SECONDS},
                )
                await asyncio.sleep(IDLE_SLEEP_SECONDS)

    async def _wrap(self, cmd: RunIngestionIterationCmd):
        try:
            await self._run_loop(cmd)
        except Exception:
            logger.exception("Error in ingestion loop")
            sys.exit(1)

    async def _run_fetch_raw_ingestion_loop(self):
        await self._run_loop(
            RunIngestionIterationCmd(
                owner=self._loop_id,
                stage="fetch_raw",
                batch_size=FETCH_RAW_BATCH_SIZE,
            )
        )

    @asynccontextmanager
    async def run(self):
        tasks = [
            asyncio.create_task(
                self._wrap(
                    RunIngestionIterationCmd(
                        owner=self._loop_id,
                        stage="fetch_raw",
                        batch_size=FETCH_RAW_BATCH_SIZE,
                    )
                )
            ),
        ]

        try:
            yield
        finally:
            for task in tasks:
                task.cancel()
            with suppress(asyncio.CancelledError):
                await asyncio.gather(*tasks)
