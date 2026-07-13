from app.contracts.uow import UnitOfWork
from app.domains.station import StationScore
from app.dto.station import (
    GetStationStatsCmd,
    RunIngestionIterationCmd,
)
from app.infra.clickhouse.repositories import StationContext
from app.infra.http.gdebenz import HTTPGdeBenzClient
from app.infra.logging import get_logger
from app.infra.postgres.uows import StationReadContext, StationWriteContext
from app.infra.redis.limit import RateLimiter
from app.services.station.add import AddStationsByAreaUC

logger = get_logger().getChild(__name__)


class StationService:
    def __init__(
        self,
        uow: UnitOfWork[StationReadContext, StationWriteContext],
        *,
        click_ctx: StationContext,
        gdebenz: HTTPGdeBenzClient,
        limiter: RateLimiter,
    ) -> None:
        self._uow = uow
        self._gdebenz = gdebenz
        self._limiter = limiter
        self._click_ctx = click_ctx

    # Async UC

    @property
    def add_by_area(self) -> AddStationsByAreaUC:
        return AddStationsByAreaUC(
            uow=self._uow,
            gdebenz=self._gdebenz,
        )

    # Single UC

    async def run_ingestion_iteration(self, cmd: RunIngestionIterationCmd) -> bool:
        from app.services.station.ingestion import RunIngestionIterationUC

        return await RunIngestionIterationUC(
            uow=self._uow,
            click_ctx=self._click_ctx,
            gdebenz=self._gdebenz,
            limiter=self._limiter,
        ).run(cmd)

    async def get_station_stats(self, cmd: GetStationStatsCmd) -> list[StationScore]:
        from app.services.station.stats import GetStationStatsUC

        return await GetStationStatsUC(
            click_ctx=self._click_ctx,
        ).run(cmd)
