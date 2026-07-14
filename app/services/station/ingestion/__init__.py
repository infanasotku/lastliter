import asyncio
import contextlib
from datetime import timedelta
from typing import AsyncGenerator

from app.contracts.uow import UnitOfWork
from app.domains.station import Station
from app.dto.ingestion import RunIngestionIterationCmd
from app.infra.clickhouse.repositories import StationContext
from app.infra.common.time import now_utc
from app.infra.http.gdebenz import HTTPGdeBenzClient
from app.infra.logging.logger import get_logger
from app.infra.postgres.uows import StationReadContext, StationWriteContext
from app.infra.redis.limit import RateLimiter
from app.services.station.ingestion.base import _HeartbeatContext, _HeartbeatStatus, _IngestionIterationUC, _station_ids

logger = get_logger().getChild(__name__)
CLAIM_FOR_SECONDS = 60 * 5  # 5 minutes
CLAIM_INTERVAL_SECONDS = 60  # 1 minute


class RunIngestionIterationUC:
    def __init__(
        self,
        cmd: RunIngestionIterationCmd,
        *,
        uow: UnitOfWork[StationReadContext, StationWriteContext],
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
        match self.cmd.stage:
            case "fetch_raw":
                from app.services.station.ingestion.raw import FetchRawObservationsUC

                return FetchRawObservationsUC(
                    self.cmd,
                    click_ctx=self._click_ctx,
                    gdebenz=self._gdebenz,
                    limiter=self._limiter,
                    hb_ctx=hb_ctx,
                )
            case _:
                raise ValueError(f"Unknown ingestion stage: {self.cmd.stage}")

    async def _claim_stations(self) -> list[Station]:
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
            stations = await ctx.stations.claim_stations(
                now=now_utc(),
                limit=self.cmd.batch_size,
                owner=owner,
                claim_for=timedelta(seconds=CLAIM_FOR_SECONDS),
            )

        logger.info(
            f"Claimed {len(stations)} stations for owner {owner}",
            extra={
                "owner": owner,
                "stations_count": len(stations),
                "station_ids": _station_ids(stations),
            },
        )
        return stations

    @contextlib.asynccontextmanager
    async def _run_heartbeat_loop(
        self,
        stations: list[Station],
        *,
        owner: str,
    ) -> AsyncGenerator[_HeartbeatContext, None]:
        hb_ctx = _HeartbeatContext(
            leased_stations=stations,
            status=_HeartbeatStatus.RUNNING,
        )
        logger.info(
            f"Starting heartbeat loop for owner {owner} with {len(stations)} stations",
            extra={
                "owner": owner,
                "stations_count": len(stations),
                "station_ids": _station_ids(stations),
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
                    refreshed = await ctx.stations.refresh_lease(
                        hb_ctx.leased_stations,
                        owner=owner,
                        claim_for=timedelta(seconds=CLAIM_FOR_SECONDS),
                        now=now_utc(),
                    )

                    if not refreshed:
                        logger.warning(
                            f"Heartbeat loop: no stations refreshed for owner {owner}, stopping loop",
                            extra={
                                "owner": owner,
                                "stations_count": len(hb_ctx.leased_stations),
                                "station_ids": _station_ids(hb_ctx.leased_stations),
                            },
                        )
                        hb_ctx.leased_stations = []
                        break
                    if refreshed != len(hb_ctx.leased_stations):
                        logger.warning(
                            f"Heartbeat loop: refreshed {refreshed} out of {len(hb_ctx.leased_stations)} stations for owner {owner}",
                            extra={
                                "owner": owner,
                                "refreshed_count": refreshed,
                                "stations_count": len(hb_ctx.leased_stations),
                                "station_ids": _station_ids(hb_ctx.leased_stations),
                            },
                        )
                        hb_ctx.leased_stations = await ctx.stations.get_claimed(owner=owner, now=now_utc())
                        logger.info(
                            f"Heartbeat loop: retained {len(hb_ctx.leased_stations)} claimed stations for owner {owner}",
                            extra={
                                "owner": owner,
                                "stations_count": len(hb_ctx.leased_stations),
                                "station_ids": _station_ids(hb_ctx.leased_stations),
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
                    "stations_count": len(hb_ctx.leased_stations),
                    "station_ids": _station_ids(hb_ctx.leased_stations),
                },
            )

    async def run(self) -> bool:
        logger.info(
            f"Starting {self.cmd.stage} ingestion iteration for owner {self.cmd.owner}", extra={"owner": self.cmd.owner}
        )
        stations = await self._claim_stations()
        if not stations:
            logger.info(f"Ingestion iteration has no work for owner {self.cmd.owner}", extra={"owner": self.cmd.owner})
            return False

        async with self._run_heartbeat_loop(stations, owner=self.cmd.owner) as hb_ctx:
            uc = self._create_dependant_uc(hb_ctx)
            await uc.run(stations)

            logger.info(
                f"Updating {self.cmd.stage} ingestion feedback for {len(stations)} stations owned by {self.cmd.owner}",
                extra={
                    "owner": self.cmd.owner,
                    "stage": self.cmd.stage,
                    "stations_count": len(stations),
                    "station_ids": _station_ids(stations),
                },
            )
            async with self._uow.begin(write=True) as ctx:
                updated_count = await ctx.stations.update_claimed_stations(
                    stations,
                    owner=self.cmd.owner,
                    now=now_utc(),
                )
            logger.info(
                f"{self.cmd.stage} ingestion feedback updated for {updated_count} out of {len(stations)} stations owned by {self.cmd.owner}",
                extra={
                    "owner": self.cmd.owner,
                    "stage": self.cmd.stage,
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
            if not hb_ctx.leased_stations:
                logger.warning(
                    f"No leased stations left for owner {self.cmd.owner}, stopping ingestion iteration",
                    extra={"owner": self.cmd.owner},
                )
                return False

        return True
