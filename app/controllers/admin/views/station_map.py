from urllib.parse import urlsplit

from sqladmin import BaseView, expose
from starlette.requests import Request
from starlette.responses import Response

from app.contracts.uow import UnitOfWork
from app.infra.postgres.uows import StationReadContext, StationWriteContext

MAP_PROTOCOL_VERSION = 1


def _get_origin(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Admin map URL must be an absolute HTTP(S) URL")
    return f"{parsed.scheme}://{parsed.netloc}"


class StationMapView(BaseView):
    name = "Map"
    icon = "fa-regular fa-map"
    category = "Stations"
    category_icon = "fa-solid fa-gas-pump"

    map_url = "http://localhost:5173"
    uow: UnitOfWork[StationReadContext, StationWriteContext] | None = None

    @expose("/stations/map", identity="station-map")
    async def station_map(self, request: Request) -> Response:
        if self.uow is None:
            raise RuntimeError("StationMapView unit of work is not configured")

        async with self.uow.begin(write=False) as ctx:
            stations = await ctx.stations.get_all()

        station_details_urls = {
            station.id: str(
                request.url_for(
                    "admin:details",
                    identity="station",
                    pk=station.id,
                )
            )
            for station in stations
        }
        map_context = {
            "type": "lastliter:admin-context",
            "version": MAP_PROTOCOL_VERSION,
            "mode": "admin",
            "capabilities": {"openStation": True},
            "stations": [
                {
                    "id": station.id,
                    "name": station.name,
                    "address": station.address,
                    "latitude": station.lat,
                    "longitude": station.lon,
                }
                for station in stations
            ],
        }

        return await self.templates.TemplateResponse(
            request,
            "station_map.html",
            {
                "map_url": self.map_url,
                "map_bridge_config": {
                    "mapOrigin": _get_origin(self.map_url),
                    "context": map_context,
                    "stationDetailsUrls": station_details_urls,
                },
            },
        )
