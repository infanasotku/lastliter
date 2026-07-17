from sqladmin import BaseView, expose
from starlette.requests import Request
from starlette.responses import Response


class StationMapView(BaseView):
    name = "Map"
    icon = "fa-regular fa-map"
    category = "Stations"
    category_icon = "fa-solid fa-gas-pump"

    map_url = "http://localhost:5173"

    @expose("/stations/map", identity="station-map")
    async def station_map(self, request: Request) -> Response:
        return await self.templates.TemplateResponse(
            request,
            "station_map.html",
            {"map_url": self.map_url},
        )
