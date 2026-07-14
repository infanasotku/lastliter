from typing import Any, Protocol

from dependency_injector.wiring import Provide, inject
from sqladmin import action, expose
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from app.container import Container
from app.domains.stats import StationScore
from app.dto.station import GetStationStatsCmd
from app.services.station import StationService


class _StationStatsView(Protocol):
    identity: str
    name_plural: str
    templates: Any

    def _station_stats_url(self, request: Request, station_id: str) -> str: ...

    def _stations_list_url(self, request: Request) -> str: ...

    async def get_stats(self, cmd: GetStationStatsCmd) -> list[StationScore]: ...


class StationStatsMixin:
    @action(
        "station-stats",
        label="Statistics",
        add_in_detail=True,
        add_in_list=False,
    )
    async def station_stats_action(self: _StationStatsView, request: Request) -> Response:
        station_id = request.query_params.get("pks", "").split(",", maxsplit=1)[0]
        if not station_id:
            return RedirectResponse(self._stations_list_url(request), status_code=303)

        return RedirectResponse(self._station_stats_url(request, station_id), status_code=303)

    @expose("/stats/{station_id}", methods=["GET"])
    async def station_stats(self: _StationStatsView, request: Request) -> Response:
        station_id = request.path_params["station_id"]
        scores = await self.get_stats(GetStationStatsCmd(station_id=station_id))

        return await self.templates.TemplateResponse(
            request,
            "station_stats.html",
            {
                "hours": range(24),
                "list_url": self._stations_list_url(request),
                "model_view": self,
                "scores": [
                    {
                        "confidence": score.confidence,
                        "hour": score.hour,
                        "score": score.score,
                        "weekday": score.weekday,
                    }
                    for score in scores
                ],
                "station_id": station_id,
                "subtitle": self.name_plural,
                "title": f"Station {station_id} statistics",
                "weekdays": enumerate(
                    ("Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"),
                    start=1,
                ),
            },
        )

    @inject
    async def get_stats(
        self,
        cmd: GetStationStatsCmd,
        #
        svc: StationService = Provide[Container.station_service],
    ) -> list[StationScore]:
        return await svc.get_station_stats(cmd)

    def _station_stats_url(self: _StationStatsView, request: Request, station_id: str) -> str:
        return str(
            request.url_for(
                f"admin:view-{self.identity}-station_stats",
                station_id=station_id,
            )
        )
