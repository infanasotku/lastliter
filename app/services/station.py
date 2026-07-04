from app.dto.station import SyncStationCmd, SyncStationResult
from app.infra.http.gdebenz import HTTPGdeBenzClient


class StationService:
    def __init__(self, *, gdebenz: HTTPGdeBenzClient) -> None:
        self._gdebenz = gdebenz

    async def sync_stations(self, cmd: SyncStationCmd) -> SyncStationResult:
        stations = await self._gdebenz.get_stations(
            lat1=cmd.lat1,
            lon1=cmd.lon1,
            lat2=cmd.lat2,
            lon2=cmd.lon2,
        )
        pass
