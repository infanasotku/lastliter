import asyncio
import contextlib
from collections.abc import AsyncGenerator
from datetime import timedelta

from app.contracts.uow import UnitOfWork
from app.domains.state import IngestionPipelineState, PipelineType
from app.dto.ingestion import RunIngestionIterationCmd
from app.infra.clickhouse.repositories import StationContext
from app.infra.common.time import now_utc
from app.infra.http.gdebenz import HTTPGdeBenzClient
from app.infra.logging.logger import get_logger
from app.infra.postgres.uows import IngestionReadContext, IngestionWriteContext
from app.infra.redis.limit import RateLimiter
from app.services.ingestion.base import _HeartbeatContext, _HeartbeatStatus, _IngestionIterationUC, _station_ids

logger = get_logger().getChild(__name__)
CLAIM_FOR_SECONDS = 60 * 5  # 5 minutes
CLAIM_INTERVAL_SECONDS = 60  # 1 minute


class RunIngestionIterationUC:
    def __init__(
        self,
        cmd: RunIngestionIterationCmd,
        *,
        uow: UnitOfWork[IngestionReadContext, IngestionWriteContext],
        click_ctx: StationContext,
        gdebenz: HTTPGdeBenzClient,
        limiter: RateLimiter,
    ):
        self.cmd = cmd

        self._uow = uow
        self._gdebenz = gdebenz
        self._limiter = limiter
        self._click_ctx = click_ctx

    def _create_dependant_uc(self, hb_ctx: _HeartbeatContext) -> _IngestionIterationUC:
        match self.cmd.pipeline_type:
            case PipelineType.FETCH_RAW:
                from app.services.ingestion.raw import FetchRawObservationsUC

                return FetchRawObservationsUC(
                    self.cmd,
                    click_ctx=self._click_ctx,
                    gdebenz=self._gdebenz,
                    limiter=self._limiter,
                    hb_ctx=hb_ctx,
                )
            case _:
                raise ValueError(f"Unknown ingestion pipeline type: {self.cmd.pipeline_type}")

    async def _claim_states(self) -> list[IngestionPipelineState]:
        owner = self.cmd.owner
        logger.info(
            f"Claiming up to {self.cmd.batch_size} stations for owner {owner}",
            extra={
                "owner": owner,
                "limit": self.cmd.batch_size,
                "claim_for_seconds": CLAIM_FOR_SECONDS,
            },
        )
        async with self._uow.begin(write=True) as ctx:
            states = await ctx.states.claim_states(
                now=now_utc(),
                limit=self.cmd.batch_size,
                owner=owner,
                claim_for=timedelta(seconds=CLAIM_FOR_SECONDS),
                pipeline_type=self.cmd.pipeline_type,
            )

        logger.info(
            f"Claimed {len(states)} stations for owner {owner}",
            extra={
                "owner": owner,
                "stations_count": len(states),
                "station_ids": _station_ids(states),
            },
        )
        return states

    @contextlib.asynccontextmanager
    async def _run_heartbeat_loop(
        self,
        states: list[IngestionPipelineState],
        *,
        owner: str,
    ) -> AsyncGenerator[_HeartbeatContext, None]:
        hb_ctx = _HeartbeatContext(
            leased_states=states,
            status=_HeartbeatStatus.RUNNING,
        )
        logger.info(
            f"Starting heartbeat loop for owner {owner} with {len(states)} stations",
            extra={
                "owner": owner,
                "stations_count": len(states),
                "station_ids": _station_ids(states),
                "claim_for_seconds": CLAIM_FOR_SECONDS,
                "heartbeat_interval_seconds": CLAIM_INTERVAL_SECONDS,
            },
        )

        async def _wrap():
            try:
                await _loop()
            except Exception as e:
                logger.error(
                    f"Heartbeat loop: error occurred for owner {owner}: {e}",
                    extra={"owner": owner, "error": str(e)},
                )
                hb_ctx.status = _HeartbeatStatus.ERROR
                hb_ctx.error = str(e)

        async def _loop():
            while True:
                async with self._uow.begin(write=True) as ctx:
                    refreshed = await ctx.states.refresh_lease(
                        hb_ctx.leased_states,
                        owner=owner,
                        claim_for=timedelta(seconds=CLAIM_FOR_SECONDS),
                        now=now_utc(),
                        pipeline_type=self.cmd.pipeline_type,
                    )

                    if not refreshed:
                        logger.warning(
                            f"Heartbeat loop: no stations refreshed for owner {owner}, stopping loop",
                            extra={
                                "owner": owner,
                                "stations_count": len(hb_ctx.leased_states),
                                "station_ids": _station_ids(hb_ctx.leased_states),
                            },
                        )
                        hb_ctx.leased_states = []
                        break
                    if refreshed != len(hb_ctx.leased_states):
                        logger.warning(
                            f"Heartbeat loop: refreshed {refreshed} out of {len(hb_ctx.leased_states)} stations for owner {owner}",
                            extra={
                                "owner": owner,
                                "refreshed_count": refreshed,
                                "stations_count": len(hb_ctx.leased_states),
                                "station_ids": _station_ids(hb_ctx.leased_states),
                            },
                        )
                        hb_ctx.leased_states = await ctx.states.get_claimed(
                            owner=owner,
                            now=now_utc(),
                            pipeline_type=self.cmd.pipeline_type,
                        )
                        logger.info(
                            f"Heartbeat loop: retained {len(hb_ctx.leased_states)} claimed states for owner {owner}",
                            extra={
                                "owner": owner,
                                "stations_count": len(hb_ctx.leased_states),
                                "station_ids": _station_ids(hb_ctx.leased_states),
                            },
                        )

                await asyncio.sleep(CLAIM_INTERVAL_SECONDS)

        task = asyncio.create_task(_wrap())

        try:
            yield hb_ctx
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

            hb_ctx.status = _HeartbeatStatus.COMPLETED
            logger.info(
                f"Heartbeat loop stopped for owner {owner}",
                extra={
                    "owner": owner,
                    "stations_count": len(hb_ctx.leased_states),
                    "station_ids": _station_ids(hb_ctx.leased_states),
                },
            )

    async def run(self) -> bool:
        logger.info(
            f"Starting {self.cmd.pipeline_type} ingestion iteration for owner {self.cmd.owner}",
            extra={"owner": self.cmd.owner},
        )
        stations = await self._claim_states()
        if not stations:
            logger.info(f"Ingestion iteration has no work for owner {self.cmd.owner}", extra={"owner": self.cmd.owner})
            return False

        async with self._run_heartbeat_loop(stations, owner=self.cmd.owner) as hb_ctx:
            uc = self._create_dependant_uc(hb_ctx)
            await uc.run(stations)

            logger.info(
                f"Updating {self.cmd.pipeline_type} ingestion feedback for {len(stations)} stations owned by {self.cmd.owner}",
                extra={
                    "owner": self.cmd.owner,
                    "pipeline_type": self.cmd.pipeline_type,
                    "stations_count": len(stations),
                    "station_ids": _station_ids(stations),
                },
            )
            async with self._uow.begin(write=True) as ctx:
                updated_count = await ctx.states.update_claimed_states(
                    stations,
                    owner=self.cmd.owner,
                    now=now_utc(),
                    pipeline_type=self.cmd.pipeline_type,
                )
            logger.info(
                f"{self.cmd.pipeline_type} ingestion feedback updated for {updated_count} out of {len(stations)} stations owned by {self.cmd.owner}",
                extra={
                    "owner": self.cmd.owner,
                    "pipeline_type": self.cmd.pipeline_type,
                    "updated_stations_count": updated_count,
                    "stations_count": len(stations),
                    "station_ids": _station_ids(stations),
                },
            )

            if hb_ctx.status == _HeartbeatStatus.ERROR:
                logger.error(
                    f"Heartbeat loop encountered an error for owner {self.cmd.owner}: {hb_ctx.error}",
                    extra={"owner": self.cmd.owner, "error": hb_ctx.error},
                )
                return False
            if not hb_ctx.leased_states:
                logger.warning(
                    f"No leased states left for owner {self.cmd.owner}, stopping ingestion iteration",
                    extra={"owner": self.cmd.owner},
                )
                return False

        return True
