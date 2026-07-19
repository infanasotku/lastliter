from app.contracts.uow import UnitOfWork
from app.domains.exception import StationNotFoundError
from app.domains.stats import StationScore
from app.dto.station import GetStationStatsCmd, StationDTO
from app.infra.clickhouse.repositories import StationContext
from app.infra.http.gdebenz import HTTPGdeBenzClient
from app.infra.logging import get_logger
from app.infra.postgres.uows import StationReadContext, StationWriteContext
from app.services.station.add import AddStationBySharedLinkUC, AddStationsByAreaUC

logger = get_logger().getChild(__name__)


class StationService:
    def __init__(
        self,
        uow: UnitOfWork[StationReadContext, StationWriteContext],
        *,
        click_ctx: StationContext,
        gdebenz: HTTPGdeBenzClient,
    ) -> None:
        self._uow = uow
        self._gdebenz = gdebenz
        self._click_ctx = click_ctx

    # Async UC

    @property
    def add_by_area(self) -> AddStationsByAreaUC:
        return AddStationsByAreaUC(
            uow=self._uow,
            gdebenz=self._gdebenz,
        )

    @property
    def add_by_shared_link(self) -> AddStationBySharedLinkUC:
        return AddStationBySharedLinkUC(
            uow=self._uow,
            gdebenz=self._gdebenz,
        )

    # Single UC

    async def get_station_stats(self, cmd: GetStationStatsCmd) -> list[StationScore]:
        from app.services.station.stats import GetStationStatsUC

        return await GetStationStatsUC(
            click_ctx=self._click_ctx,
        ).run(cmd)

    async def get_all_stations(self) -> list[StationDTO]:
        from app.services.station.get import GetAllStationsUC

        return await GetAllStationsUC(
            uow=self._uow,
            click_ctx=self._click_ctx,
        ).run()

    # Common

    async def get_link_by_station_id(self, station_id: str) -> str:
        async with self._uow.begin(write=False) as ctx:
            s = await ctx.stations.get_by_id(station_id)
            if s is None:
                raise StationNotFoundError(f"Station with id {station_id} not found")

        return await self._gdebenz.get_shared_link_by_station_id(station_id)
