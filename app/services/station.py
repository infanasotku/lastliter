from app.contracts.uow import UnitOfWork
from app.dto.station import SyncStationCmd, SyncStationResult
from app.infra.http.gdebenz import HTTPGdeBenzClient
from app.infra.postgres.uows import StationReadContext, StationWriteContext


class StationService:
    def __init__(
        self,
        uow: UnitOfWork[StationReadContext, StationWriteContext],
        *,
        gdebenz: HTTPGdeBenzClient,
    ) -> None:
        self._uow = uow
        self._gdebenz = gdebenz

    async def sync_stations(self, cmd: SyncStationCmd) -> SyncStationResult:
        stations = await self._gdebenz.get_stations(
            lat1=cmd.lat1,
            lon1=cmd.lon1,
            lat2=cmd.lat2,
            lon2=cmd.lon2,
        )
        filtered_stations = [s for s in stations if s.address != "" and s.name != ""]
        async with self._uow.begin(write=True) as uow:
            inserted_stations = await uow.stations.insert_many_safe(filtered_stations)

        return SyncStationResult(
            new=inserted_stations,
        )
